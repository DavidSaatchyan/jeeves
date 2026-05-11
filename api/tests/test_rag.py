"""Unit tests for app.rag — mocking ChromaDB and OpenAI."""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app import rag


@pytest.fixture(autouse=True)
def reset_rag_globals():
    """Reset module-level globals between tests."""
    rag._chroma_client = None
    yield
    rag._chroma_client = None


@pytest.fixture
def tenant_id() -> UUID:
    return uuid4()


@pytest.fixture
def file_id() -> UUID:
    return uuid4()


@pytest.fixture
def mock_chroma():
    """Mock ChromaDB collection with a chain of mocks."""
    col = MagicMock(name="collection")
    col.count.return_value = 5
    col.name = "test_collection"

    # Mock the client
    client = MagicMock(name="chroma_client")
    client.get_or_create_collection.return_value = col

    with patch("app.rag._chroma", return_value=client):
        # Also patch the module-level client so _chroma() returns our mock
        with patch.object(rag, "_chroma_client", client):
            yield col, client


@pytest.fixture
def mock_openai():
    """Mock OpenAI embedding responses."""
    mock_client = MagicMock(name="openai_client")
    # embed_batch response
    fake_data = [MagicMock(embedding=[0.1, 0.2, 0.3])]

    mock_response = MagicMock()
    mock_response.data = fake_data

    mock_client.embeddings.create.return_value = mock_response

    with patch("app.rag.OpenAI", return_value=mock_client):
        yield mock_client


# ── embed_batch ────────────────────────────────────────────────────────────


class TestEmbedBatch:
    def test_empty_list(self, mock_openai):
        assert rag.embed_batch([]) == []

    def test_single_text(self, mock_openai):
        result = rag.embed_batch(["hello"])
        assert len(result) == 1
        assert result[0] == [0.1, 0.2, 0.3]

    def test_multiple_texts(self, mock_openai):
        # Need to adjust mock for multiple texts
        from unittest.mock import MagicMock
        mock_client = MagicMock()
        fake_data = [
            MagicMock(embedding=[0.1, 0.2]),
            MagicMock(embedding=[0.3, 0.4]),
        ]
        mock_response = MagicMock()
        mock_response.data = fake_data
        mock_client.embeddings.create.return_value = mock_response

        with patch("app.rag.OpenAI", return_value=mock_client):
            result = rag.embed_batch(["a", "b"])
            assert len(result) == 2


# ── index_file ─────────────────────────────────────────────────────────────


class TestIndexFile:
    def test_index_success(self, tenant_id, file_id, mock_chroma, mock_openai, tmp_path):
        col, _ = mock_chroma
        p = tmp_path / "test.txt"
        p.write_text("Hello world. " * 20)

        n = rag.index_file(tenant_id, file_id, p)
        assert n > 0
        col.delete.assert_called_once_with(where={"file_id": str(file_id)})
        col.add.assert_called_once()

    def test_index_empty_file(self, tenant_id, file_id, mock_chroma, mock_openai, tmp_path):
        col, _ = mock_chroma
        p = tmp_path / "empty.txt"
        p.write_text("")

        n = rag.index_file(tenant_id, file_id, p)
        assert n == 0
        col.add.assert_not_called()

    def test_index_with_delete_error(self, tenant_id, file_id, mock_chroma, mock_openai, tmp_path):
        col, _ = mock_chroma
        col.delete.side_effect = Exception("Chroma not ready")

        p = tmp_path / "test.txt"
        p.write_text("Hello. " * 20)

        n = rag.index_file(tenant_id, file_id, p)
        assert n > 0  # still proceeds to add
        col.add.assert_called_once()


# ── delete_file ────────────────────────────────────────────────────────────


class TestDeleteFile:
    def test_delete_existing(self, tenant_id, file_id, mock_chroma):
        col, _ = mock_chroma
        rag.delete_file(tenant_id, file_id)
        col.delete.assert_called_once_with(where={"file_id": str(file_id)})

    def test_delete_nonexistent(self, tenant_id, file_id, mock_chroma):
        col, _ = mock_chroma
        col.delete.side_effect = Exception("Not found")
        rag.delete_file(tenant_id, file_id)  # should not raise

    def test_delete_logs_counts(self, tenant_id, file_id, mock_chroma):
        col, _ = mock_chroma
        col.count.side_effect = [10, 3]  # before, after
        rag.delete_file(tenant_id, file_id)
        assert col.count.call_count >= 2


# ── search ─────────────────────────────────────────────────────────────────


class TestSearch:
    def test_search_empty_collection(self, tenant_id, mock_chroma, mock_openai):
        col, _ = mock_chroma
        col.count.return_value = 0
        result = rag.search(tenant_id, "test query")
        assert result == []

    def test_search_below_threshold_returns_results(self, tenant_id, mock_chroma, mock_openai):
        col, _ = mock_chroma
        col.count.return_value = 2
        col.query.return_value = {
            "ids": [["id1", "id2"]],
            "documents": [["doc1", "doc2"]],
            "metadatas": [[{"chunk_hash": "h1", "filename": "a.txt"}, {"chunk_hash": "h2", "filename": "b.txt"}]],
            "distances": [[0.2, 0.3]],
        }
        result = rag.search(tenant_id, "test", threshold=0.5)
        assert len(result) == 2
        assert result[0]["distance"] == 0.2
        assert result[0]["score"] == 0.8

    def test_search_above_threshold_returns_empty(self, tenant_id, mock_chroma, mock_openai):
        col, _ = mock_chroma
        col.count.return_value = 2
        col.query.return_value = {
            "ids": [["id1"]],
            "documents": [["some doc"]],
            "metadatas": [[{"chunk_hash": "h1", "filename": "a.txt"}]],
            "distances": [[0.9]],
        }
        result = rag.search(tenant_id, "test", threshold=0.5)
        assert result == []

    def test_search_deduplicates_by_chunk_hash(self, tenant_id, mock_chroma, mock_openai):
        col, _ = mock_chroma
        col.count.return_value = 3
        col.query.return_value = {
            "ids": [["id1", "id2", "id3"]],
            "documents": [["same content", "same content", "other"]],
            "metadatas": [[
                {"chunk_hash": "abc", "filename": "a.txt"},
                {"chunk_hash": "abc", "filename": "a.txt"},
                {"chunk_hash": "def", "filename": "a.txt"},
            ]],
            "distances": [[0.2, 0.3, 0.4]],
        }
        result = rag.search(tenant_id, "test", threshold=0.99)
        assert len(result) == 2  # dedup removes one
        hashes = [r["chunk_hash"] for r in result]
        assert hashes == ["abc", "def"]

    def test_search_without_chunk_hash(self, tenant_id, mock_chroma, mock_openai):
        col, _ = mock_chroma
        col.count.return_value = 1
        col.query.return_value = {
            "ids": [["id1"]],
            "documents": [["doc"]],
            "metadatas": [[{}]],  # no chunk_hash
            "distances": [[0.3]],
        }
        result = rag.search(tenant_id, "test", threshold=0.5)
        assert len(result) == 1  # still included
        assert result[0]["chunk_hash"] == ""

    def test_search_exception_returns_empty(self, tenant_id, mock_chroma):
        col, _ = mock_chroma
        col.count.side_effect = Exception("Chroma down")
        result = rag.search(tenant_id, "test")
        assert result == []

    def test_search_custom_top_k(self, tenant_id, mock_chroma, mock_openai):
        col, _ = mock_chroma
        col.count.return_value = 100
        rag.search(tenant_id, "test", top_k=3, threshold=0.99)
        col.query.assert_called_once()
        call_kwargs = col.query.call_args[1]
        assert call_kwargs["n_results"] == 3

    def test_search_with_none_metadatas(self, tenant_id, mock_chroma, mock_openai):
        col, _ = mock_chroma
        col.count.return_value = 1
        col.query.return_value = {
            "ids": [["id1"]],
            "documents": [["doc"]],
            "metadatas": [[None]],
            "distances": [[0.3]],
        }
        result = rag.search(tenant_id, "test", threshold=0.5)
        assert len(result) == 1


# ── deduplicate_collection ─────────────────────────────────────────────────


class TestDeduplicateCollection:
    def test_no_duplicates(self, tenant_id, mock_chroma):
        col, _ = mock_chroma
        col.get.return_value = {
            "ids": ["id1", "id2"],
            "metadatas": [
                {"filename": "a.txt", "chunk_hash": "h1"},
                {"filename": "a.txt", "chunk_hash": "h2"},
            ],
        }
        result = rag.deduplicate_collection(tenant_id)
        assert result["removed"] == 0
        assert result["total"] == 2
        col.delete.assert_not_called()

    def test_duplicates_removed(self, tenant_id, mock_chroma):
        col, _ = mock_chroma
        col.get.return_value = {
            "ids": ["id1", "id2", "id3"],
            "metadatas": [
                {"filename": "a.txt", "chunk_hash": "h1"},
                {"filename": "a.txt", "chunk_hash": "h1"},
                {"filename": "a.txt", "chunk_hash": "h2"},
            ],
        }
        result = rag.deduplicate_collection(tenant_id)
        assert result["removed"] == 1
        assert result["total"] == 3
        col.delete.assert_called_once_with(ids=["id2"])

    def test_empty_collection(self, tenant_id, mock_chroma):
        col, _ = mock_chroma
        col.count.return_value = 0
        result = rag.deduplicate_collection(tenant_id)
        assert result["removed"] == 0
        assert result["total"] == 0


# ── purge_orphans ──────────────────────────────────────────────────────────


class TestPurgeOrphans:
    def test_no_orphans(self, tenant_id, mock_chroma):
        col, _ = mock_chroma
        col.get.return_value = {
            "ids": ["id1", "id2"],
            "metadatas": [
                {"file_id": "f1"},
                {"file_id": "f2"},
            ],
        }
        result = rag.purge_orphans(tenant_id, {"f1", "f2"})
        assert result["removed"] == 0
        assert result["total"] == 2
        col.delete.assert_not_called()

    def test_orphans_removed(self, tenant_id, mock_chroma):
        col, _ = mock_chroma
        col.get.return_value = {
            "ids": ["id1", "id2", "id3"],
            "metadatas": [
                {"file_id": "f1"},
                {"file_id": "f2"},
                {"file_id": "f3"},
            ],
        }
        result = rag.purge_orphans(tenant_id, {"f1"})
        assert result["removed"] == 2
        col.delete.assert_called_once()

    def test_empty_collection(self, tenant_id, mock_chroma):
        col, _ = mock_chroma
        col.count.return_value = 0
        result = rag.purge_orphans(tenant_id, set())
        assert result["removed"] == 0
        assert result["total"] == 0

    def test_missing_file_id_in_meta(self, tenant_id, mock_chroma):
        col, _ = mock_chroma
        col.get.return_value = {
            "ids": ["id1"],
            "metadatas": [{"filename": "orphan.txt"}],  # no file_id
        }
        result = rag.purge_orphans(tenant_id, set())
        assert result["removed"] == 1  # missing file_id → treated as orphan


# ── _collection ────────────────────────────────────────────────────────────


class TestCollection:
    def test_collection_name_format(self, tenant_id, mock_chroma):
        col, client = mock_chroma
        _ = rag._collection(tenant_id)
        expected_name = f"tenant_{str(tenant_id).replace('-', '')}"
        client.get_or_create_collection.assert_called_once()
        call_name = client.get_or_create_collection.call_args[1]["name"]
        assert call_name == expected_name

    def test_collection_name_str_tenant(self, mock_chroma):
        col, client = mock_chroma
        _ = rag._collection("some-tenant-id")
        expected = "tenant_sometenantid"
        call_name = client.get_or_create_collection.call_args[1]["name"]
        assert call_name == expected


# ── _count_all_chunks ──────────────────────────────────────────────────────


class TestCountAllChunks:
    def test_returns_count(self, tenant_id, mock_chroma):
        col, _ = mock_chroma
        col.count.return_value = 42
        assert rag._count_all_chunks(tenant_id) == 42

    def test_exception_returns_zero(self, tenant_id, mock_chroma):
        col, _ = mock_chroma
        col.count.side_effect = Exception("Error")
        assert rag._count_all_chunks(tenant_id) == 0


# ── _chroma singleton ──────────────────────────────────────────────────────


class TestChromaSingleton:
    def test_singleton_behavior(self):
        rag._chroma_client = None
        with patch("app.rag.chromadb.PersistentClient") as mock_pc:
            with patch("app.rag._settings.chroma_path", "/tmp/chroma"):
                with patch("app.rag._settings.chroma_url", ""):
                    c1 = rag._chroma()
                    c2 = rag._chroma()
                    assert c1 is c2
                    mock_pc.assert_called_once()

    def test_no_config_raises(self):
        rag._chroma_client = None
        with patch("app.rag._settings.chroma_path", ""):
            with patch("app.rag._settings.chroma_url", ""):
                with pytest.raises(RuntimeError, match="Neither CHROMA_URL nor CHROMA_PATH"):
                    rag._chroma()
