"""Integration tests for knowledge.py FastAPI routes.

Uses TestClient with overridden dependencies (auth, db) and
mocked rag/chunking internals.
"""
from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import ANY, AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.knowledge import MAX_SIZE_MB


# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture
def mock_db():
    db = MagicMock(spec=Session)
    return db


@pytest.fixture
def override_deps(app, mock_tenant, mock_db):
    from app.auth import get_current_tenant
    from app.db import get_db

    app.dependency_overrides[get_current_tenant] = lambda: mock_tenant
    app.dependency_overrides[get_db] = lambda: mock_db
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client(app, override_deps):
    with TestClient(app) as c:
        yield c


@pytest.fixture
def mock_rag():
    patches = {
        "index_file": MagicMock(return_value=5),
        "index_text": MagicMock(return_value=4),
        "index_structured_text": MagicMock(return_value=6),
        "search": MagicMock(return_value=[
            {"text": "chunk1", "score": 0.9, "filename": "doc.txt", "section": "", "distance": 0.1}
        ]),
        "delete_file": MagicMock(),
        "get_chunks_for_file": MagicMock(return_value=[]),
        "purge_orphans": MagicMock(return_value={"purged": 0}),
        "deduplicate_collection": MagicMock(return_value={"removed": 0}),
    }
    with patch.multiple("app.knowledge.rag", **patches):
        yield patches


@pytest.fixture
def mock_chunking():
    """Use side_effect so sanitize_filename transforms input instead of
    returning a hardcoded value — this lets extension-validation tests work."""
    def _sanitize(name):
        from app.rag.chunking import sanitize_filename as real_sf
        return real_sf(name)

    with patch("app.knowledge.sanitize_filename", side_effect=_sanitize) as sf:
        with patch("app.knowledge.file_sha256", return_value="abcdef123456"):
            yield sf


@pytest.fixture
def mock_openai_chat():
    """Patch openai.AsyncOpenAI so knowledge.py's lazy import uses our mock.
    Uses AsyncMock for the create method since MagicMock is not awaitable."""
    mock_completion = MagicMock()
    mock_completion.choices = [MagicMock(message=MagicMock(content="Mocked response."))]

    create_mock = AsyncMock(return_value=mock_completion)
    completions_mock = MagicMock()
    completions_mock.create = create_mock
    chat_mock = MagicMock()
    chat_mock.completions = completions_mock
    client_mock = MagicMock()
    client_mock.chat = chat_mock

    with patch("openai.AsyncOpenAI", return_value=client_mock):
        yield


def _mock_db_execute_first(db: MagicMock, return_value):
    """Set up mock_db.execute(select(...).order_by(...)).scalars().first() = return_value."""
    result = MagicMock()
    scalars_result = MagicMock()
    scalars_result.first.return_value = return_value
    result.scalars.return_value = scalars_result
    db.execute.return_value = result


def _mock_db_execute_all(db: MagicMock, return_value):
    """Set up mock_db.execute(...).scalars().all() = return_value."""
    result = MagicMock()
    scalars_result = MagicMock()
    scalars_result.all.return_value = return_value
    result.scalars.return_value = scalars_result
    db.execute.return_value = result


def _mock_db_execute_scalar_one_or_none(db: MagicMock, return_value):
    """Set up mock_db.execute(...).scalar_one_or_none() = return_value.
    Also handles .scalars().first() chain used by dedup queries."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = return_value
    scalars_mock = MagicMock()
    scalars_mock.first.return_value = return_value
    result.scalars.return_value = scalars_mock
    db.execute.return_value = result


# ── Batch upload tests ────────────────────────────────────────────────────


class TestUploadFilesBatch:
    def test_empty_list(self, client, mock_db, mock_rag, mock_chunking, tmp_path):
        with patch("app.knowledge._settings.knowledge_dir", str(tmp_path)):
            resp = client.post("/knowledge/files/batch", files=[])
        assert resp.status_code == 201
        assert resp.json() == {"results": []}

    def test_single_file_success(self, client, mock_db, mock_rag, mock_chunking, tmp_path):
        _mock_db_execute_first(mock_db, None)
        mock_db.add.return_value = None
        with patch("app.knowledge._settings.knowledge_dir", str(tmp_path)):
            resp = client.post(
                "/knowledge/files/batch",
                files=[("files", ("hello.txt", io.BytesIO(b"hello"), "text/plain"))],
            )
        assert resp.status_code == 201
        data = resp.json()
        assert len(data["results"]) == 1
        r = data["results"][0]
        assert r["status"] == "processing"
        assert r["duplicate"] is None
        assert "id" in r
        assert r["filename"] == "hello.txt"

    def test_multiple_files_all_succeed(self, client, mock_db, mock_rag, mock_chunking, tmp_path):
        _mock_db_execute_first(mock_db, None)
        mock_db.add.return_value = None
        with patch("app.knowledge._settings.knowledge_dir", str(tmp_path)):
            resp = client.post(
                "/knowledge/files/batch",
                files=[
                    ("files", ("a.txt", io.BytesIO(b"aaa"), "text/plain")),
                    ("files", ("b.txt", io.BytesIO(b"bbb"), "text/plain")),
                    ("files", ("c.txt", io.BytesIO(b"ccc"), "text/plain")),
                ],
            )
        assert resp.status_code == 201
        data = resp.json()
        assert len(data["results"]) == 3
        for r in data["results"]:
            assert r["status"] == "processing"
            assert r["duplicate"] is None
            assert "id" in r

    def test_mixed_valid_and_invalid_extensions(self, client, mock_db, mock_rag, mock_chunking, tmp_path):
        _mock_db_execute_first(mock_db, None)
        mock_db.add.return_value = None
        with patch("app.knowledge._settings.knowledge_dir", str(tmp_path)):
            resp = client.post(
                "/knowledge/files/batch",
                files=[
                    ("files", ("good.txt", io.BytesIO(b"ok"), "text/plain")),
                    ("files", ("bad.exe", io.BytesIO(b"nope"), "application/octet-stream")),
                    ("files", ("also_good.md", io.BytesIO(b"fine"), "text/markdown")),
                ],
            )
        assert resp.status_code == 201
        data = resp.json()
        assert len(data["results"]) == 3
        assert data["results"][0]["status"] == "processing"
        assert data["results"][1]["error"] is not None
        assert "Unsupported" in data["results"][1]["error"]
        assert data["results"][2]["status"] == "processing"

    def test_duplicate_in_batch(self, client, mock_db, mock_rag, mock_chunking, tmp_path):
        existing = MagicMock()
        existing.id = uuid4()
        existing.status = "ready"
        existing.filename = "dup.txt"
        # First file: no duplicate; second file: duplicate
        mock_db.execute.return_value.scalars.return_value.first.side_effect = [None, existing]
        mock_db.add.return_value = None
        with patch("app.knowledge._settings.knowledge_dir", str(tmp_path)):
            resp = client.post(
                "/knowledge/files/batch",
                files=[
                    ("files", ("new.txt", io.BytesIO(b"new content"), "text/plain")),
                    ("files", ("dup.txt", io.BytesIO(b"existing content"), "text/plain")),
                ],
            )
        assert resp.status_code == 201
        data = resp.json()
        assert len(data["results"]) == 2
        assert data["results"][0]["status"] == "processing"
        assert data["results"][0]["duplicate"] is None
        assert data["results"][1]["duplicate"] is True
        assert str(existing.id) == data["results"][1]["id"]

    def test_total_size_exceeded(self, client, mock_db, mock_rag, mock_chunking, tmp_path):
        _mock_db_execute_first(mock_db, None)
        oversized = b"x" * (MAX_SIZE_MB * 1024 * 1024 + 1)
        with patch("app.knowledge._settings.knowledge_dir", str(tmp_path)):
            resp = client.post(
                "/knowledge/files/batch",
                files=[("files", ("big.txt", io.BytesIO(oversized), "text/plain"))],
            )
        assert resp.status_code == 413

    def test_folder_not_found(self, client, mock_db, mock_rag, mock_chunking, tmp_path):
        _mock_db_execute_scalar_one_or_none(mock_db, None)  # folder lookup returns None
        with patch("app.knowledge._settings.knowledge_dir", str(tmp_path)):
            resp = client.post(
                "/knowledge/files/batch",
                files=[("files", ("a.txt", io.BytesIO(b"data"), "text/plain"))],
                data={"folder_id": str(uuid4())},
            )
        assert resp.status_code == 404


# ── Upload tests ───────────────────────────────────────────────────────────


class TestUploadFile:
    def test_upload_success(self, client, mock_db, mock_rag, mock_chunking, tmp_path):
        _mock_db_execute_first(mock_db, None)
        mock_db.add.return_value = None

        with patch("app.knowledge._settings.knowledge_dir", str(tmp_path)):
            resp = client.post(
                "/knowledge/files",
                files={"file": ("test.txt", io.BytesIO(b"hello world"), "text/plain")},
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "processing"
        assert "id" in data

    def test_upload_duplicate(self, client, mock_db, mock_rag, mock_chunking, tmp_path):
        fake_rec = MagicMock()
        fake_rec.id = uuid4()
        fake_rec.status = "ready"
        fake_rec.filename = "test.txt"
        _mock_db_execute_first(mock_db, fake_rec)

        with patch("app.knowledge._settings.knowledge_dir", str(tmp_path)):
            resp = client.post(
                "/knowledge/files",
                files={"file": ("test.txt", io.BytesIO(b"hello world"), "text/plain")},
            )
        assert resp.status_code == 201
        assert resp.json()["duplicate"] is True

    def test_upload_unsupported_extension(self, client, mock_db, mock_rag, mock_chunking):
        resp = client.post(
            "/knowledge/files",
            files={"file": ("test.exe", io.BytesIO(b"binary data"), "application/octet-stream")},
        )
        assert resp.status_code == 400
        assert "Unsupported" in resp.text

    def test_upload_too_large(self, client, mock_db, mock_rag, mock_chunking, tmp_path):
        _mock_db_execute_first(mock_db, None)

        big_data = b"x" * (MAX_SIZE_MB * 1024 * 1024 + 1)
        with patch("app.knowledge._settings.knowledge_dir", str(tmp_path)):
            resp = client.post(
                "/knowledge/files",
                files={"file": ("big.txt", io.BytesIO(big_data), "text/plain")},
            )
        assert resp.status_code == 413

    def test_upload_size_at_limit(self, client, mock_db, mock_rag, mock_chunking, tmp_path):
        _mock_db_execute_first(mock_db, None)

        data_at_limit = b"x" * (MAX_SIZE_MB * 1024 * 1024)
        with patch("app.knowledge._settings.knowledge_dir", str(tmp_path)):
            resp = client.post(
                "/knowledge/files",
                files={"file": ("at_limit.txt", io.BytesIO(data_at_limit), "text/plain")},
            )
        assert resp.status_code == 201

    def test_upload_no_filename(self, client, mock_db, mock_rag, mock_chunking, tmp_path):
        _mock_db_execute_first(mock_db, None)

        with patch("app.knowledge._settings.knowledge_dir", str(tmp_path)):
            resp = client.post(
                "/knowledge/files",
                files={"file": ("", io.BytesIO(b"data"), "text/plain")},
            )
        # Empty filename → sanitize yields "unnamed"
        assert resp.status_code in (201, 422)

    def test_upload_background_index_called(self, client, mock_db, mock_rag, mock_chunking, tmp_path):
        _mock_db_execute_first(mock_db, None)

        with patch("app.knowledge._settings.knowledge_dir", str(tmp_path)):
            with patch("app.knowledge.asyncio.create_task") as mock_task:
                resp = client.post(
                    "/knowledge/files",
                    files={"file": ("test.txt", io.BytesIO(b"hello"), "text/plain")},
                )
        assert resp.status_code == 201
        mock_task.assert_called_once()


# ── List files ─────────────────────────────────────────────────────────────


class TestListFiles:
    def test_list_empty(self, client, mock_db, mock_rag):
        _mock_db_execute_all(mock_db, [])
        resp = client.get("/knowledge/files")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_with_files(self, client, mock_db, mock_rag):
        from datetime import datetime
        from app.models import FileRecord

        f1 = FileRecord(
            id=uuid4(), tenant_id=uuid4(), filename="a.txt",
            status="ready", size_bytes=100, chunks_total=5,
            created_at=datetime(2025, 1, 1),
        )
        f2 = FileRecord(
            id=uuid4(), tenant_id=uuid4(), filename="b.txt",
            status="failed", size_bytes=200, chunks_total=0,
            error="processing error",
            created_at=datetime(2025, 1, 2),
        )
        _mock_db_execute_all(mock_db, [f1, f2])

        resp = client.get("/knowledge/files")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["filename"] == "a.txt"
        assert data[0]["status"] == "ready"
        assert data[1]["filename"] == "b.txt"
        assert data[1]["error"] == "processing error"


# ── Delete file ────────────────────────────────────────────────────────────


class TestDeleteFile:
    def test_delete_existing(self, client, mock_db, mock_rag, tmp_path):
        file_id = uuid4()
        rec = MagicMock()
        rec.id = file_id
        rec.filename = "test.txt"
        rec.tenant_id = uuid4()
        rec.s3_key = str(tmp_path / "test.txt")

        _mock_db_execute_scalar_one_or_none(mock_db, rec)

        resp = client.delete(f"/knowledge/files/{file_id}")
        assert resp.status_code == 204
        mock_db.delete.assert_called_once_with(rec)
        mock_db.commit.assert_called()
        mock_rag["delete_file"].assert_called_once()

    def test_delete_not_found(self, client, mock_db, mock_rag):
        _mock_db_execute_scalar_one_or_none(mock_db, None)
        file_id = uuid4()
        resp = client.delete(f"/knowledge/files/{file_id}")
        assert resp.status_code == 404

    def test_delete_chroma_failure_logged(self, client, mock_db, mock_rag, tmp_path):
        file_id = uuid4()
        rec = MagicMock()
        rec.id = file_id
        rec.filename = "test.txt"
        rec.tenant_id = uuid4()
        rec.s3_key = str(tmp_path / "test.txt")

        _mock_db_execute_scalar_one_or_none(mock_db, rec)
        mock_rag["delete_file"].side_effect = Exception("Chroma error")

        resp = client.delete(f"/knowledge/files/{file_id}")
        assert resp.status_code == 204

    def test_delete_missing_physical_file(self, client, mock_db, mock_rag):
        file_id = uuid4()
        rec = MagicMock()
        rec.id = file_id
        rec.filename = "ghost.txt"
        rec.tenant_id = uuid4()
        rec.s3_key = "/nonexistent/path/file.txt"

        _mock_db_execute_scalar_one_or_none(mock_db, rec)

        resp = client.delete(f"/knowledge/files/{file_id}")
        assert resp.status_code == 204


# ── Simulate (RAG Simulator, replaces /knowledge/chat) ──────────────────────


class TestSimulate:
    def test_simulate_with_context(self, client, mock_db, mock_rag, mock_openai_chat):
        mock_rag["search"].return_value = [
            {"text": "Relevant context here.", "score": 0.95, "filename": "doc.txt", "section": "Test", "distance": 0.05}
        ]

        resp = client.post("/knowledge/simulate", json={"query": "What is this about?", "top_k": 5})
        assert resp.status_code == 200
        data = resp.json()
        assert data["answer"] == "Mocked response."
        assert "sources" in data

    def test_simulate_without_context(self, client, mock_db, mock_rag, mock_openai_chat):
        mock_rag["search"].return_value = []

        resp = client.post("/knowledge/simulate", json={"query": "Tell me something."})
        assert resp.status_code == 200
        data = resp.json()
        assert data["answer"] == "Mocked response."
        assert data["sources"] == []

    def test_simulate_empty_query(self, client, mock_db, mock_rag, mock_openai_chat):
        mock_rag["search"].return_value = []

        resp = client.post("/knowledge/simulate", json={"query": ""})
        assert resp.status_code == 400

    def test_simulate_openai_error(self, client, mock_db, mock_rag):
        mock_rag["search"].return_value = []

        with patch("openai.AsyncOpenAI") as mock_oa:
            mock_oa.return_value.chat.completions.create.side_effect = Exception("API error")
            with pytest.raises(Exception):
                client.post("/knowledge/simulate", json={"query": "Hi"})


# ── Cleanup ────────────────────────────────────────────────────────────────


class TestCleanup:
    def test_cleanup_returns_stats(self, client, mock_db, mock_rag):
        fid = uuid4()
        rec1 = MagicMock()
        rec1.id = fid
        _mock_db_execute_all(mock_db, [rec1])
        mock_rag["purge_orphans"].return_value = {"total": 10, "removed": 2}
        mock_rag["deduplicate_collection"].return_value = {"total": 8, "removed": 1}

        resp = client.post("/knowledge/cleanup")
        assert resp.status_code == 200
        data = resp.json()
        assert "purge" in data
        assert "dedup" in data
        mock_rag["purge_orphans"].assert_called_once_with(ANY, {str(fid)})

    def test_cleanup_no_files(self, client, mock_db, mock_rag):
        _mock_db_execute_all(mock_db, [])
        resp = client.post("/knowledge/cleanup")
        assert resp.status_code == 200


# ── Background index ───────────────────────────────────────────────────────


class TestBackgroundIndex:
    @pytest.mark.asyncio
    async def test_index_success_updates_db(self, mock_rag):
        from app.knowledge import _background_index
        from sqlalchemy.sql.elements import TextClause

        tenant_id = uuid4()
        file_id = uuid4()
        path = Path("/tmp/test.txt")

        mock_rag["index_file"].return_value = 7

        with patch("app.knowledge.engine.begin") as mock_begin:
            mock_conn = MagicMock()
            mock_begin.return_value.__enter__.return_value = mock_conn
            await _background_index(tenant_id, file_id, path)
            mock_conn.execute.assert_called_once()
            call_args = mock_conn.execute.call_args[0]
            assert isinstance(call_args[0], TextClause)

    @pytest.mark.asyncio
    async def test_index_failure_marks_failed(self, mock_rag):
        from app.knowledge import _background_index

        tenant_id = uuid4()
        file_id = uuid4()
        path = Path("/tmp/test.txt")

        mock_rag["index_file"].side_effect = ValueError("Index failed")

        with patch("app.knowledge.engine.begin") as mock_begin:
            mock_conn = MagicMock()
            mock_begin.return_value.__enter__.return_value = mock_conn
            await _background_index(tenant_id, file_id, path)
            assert mock_conn.execute.call_count >= 1
            call_text = str(mock_conn.execute.call_args[0][0])
            assert "failed" in call_text

    @pytest.mark.asyncio
    async def test_index_db_update_failure_logged(self, mock_rag):
        from app.knowledge import _background_index

        tenant_id = uuid4()
        file_id = uuid4()
        path = Path("/tmp/test.txt")

        mock_rag["index_file"].side_effect = ValueError("Index failed")

        with patch("app.knowledge.engine.begin") as mock_begin:
            mock_begin.return_value.__enter__.side_effect = Exception("DB error")
            await _background_index(tenant_id, file_id, path)


# ── Background URL index ───────────────────────────────────────────────────


class TestBackgroundIndexUrl:
    @pytest.mark.asyncio
    async def test_index_url_success_updates_db(self, mock_rag):
        from app.knowledge import _background_index_url

        tenant_id = uuid4()
        url_id = uuid4()

        mock_rag["index_structured_text"].return_value = 7

        with patch("app.knowledge.url_extractor.fetch_url_structured", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = ("Page Title", [("", "Extracted text content")])
            with patch("app.knowledge.engine.begin") as mock_begin:
                mock_conn = MagicMock()
                mock_begin.return_value.__enter__.return_value = mock_conn
                await _background_index_url(tenant_id, url_id, "https://example.com", None)
                mock_conn.execute.assert_called_once()
                mock_rag["index_structured_text"].assert_called_once_with(tenant_id, url_id, [("", "Extracted text content")], "Page Title")

    @pytest.mark.asyncio
    async def test_index_url_failure_marks_failed(self, mock_rag):
        from app.knowledge import _background_index_url

        tenant_id = uuid4()
        url_id = uuid4()

        mock_rag["index_structured_text"].side_effect = ValueError("Index failed")

        with patch("app.knowledge.url_extractor.fetch_url_structured", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = ("Title", [("", "text")])
            with patch("app.knowledge.engine.begin") as mock_begin:
                mock_conn = MagicMock()
                mock_begin.return_value.__enter__.return_value = mock_conn
                await _background_index_url(tenant_id, url_id, "https://example.com", None)
                call_text = str(mock_conn.execute.call_args[0][0])
                assert "failed" in call_text


# ── URL import ──────────────────────────────────────────────────────────────


@patch("app.knowledge.asyncio.create_task", MagicMock())
class TestImportUrl:
    def test_import_url_success(self, client, mock_db, mock_rag, mock_chunking):
        _mock_db_execute_scalar_one_or_none(mock_db, None)
        resp = client.post("/knowledge/urls", json={"url": "https://example.com/page", "title": "Test Page"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "processing"
        assert "id" in data
        assert data["url"] == "https://example.com/page"
        assert mock_db.add.called
        # First add call should be the KnowledgeUrl
        first_args = mock_db.add.call_args_list[0][0][0]
        assert first_args.url == "https://example.com/page"

    def test_import_url_empty_raises(self, client, mock_db, mock_rag, mock_chunking):
        resp = client.post("/knowledge/urls", json={"url": "", "title": "Test"})
        assert resp.status_code == 400

    def test_import_url_folder_not_found(self, client, mock_db, mock_rag, mock_chunking):
        _mock_db_execute_scalar_one_or_none(mock_db, None)
        resp = client.post("/knowledge/urls", json={
            "url": "https://example.com", "title": "Test", "folder_id": str(uuid4()),
        })
        assert resp.status_code == 404

    def test_import_url_empty_title_raises(self, client, mock_db, mock_rag, mock_chunking):
        resp = client.post("/knowledge/urls", json={"url": "https://example.com/page", "title": ""})
        assert resp.status_code == 400

    def test_list_urls(self, client, mock_db, mock_rag):
        mock_rec = MagicMock()
        mock_rec.id = uuid4()
        mock_rec.url = "https://example.com"
        mock_rec.title = "Test"
        mock_rec.status = "ready"
        mock_rec.folder_id = None
        mock_rec.chunks_total = 5
        mock_rec.error = None
        mock_rec.created_at = None
        _mock_db_execute_all(mock_db, [mock_rec])
        resp = client.get("/knowledge/urls")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["url"] == "https://example.com"

    def test_delete_url(self, client, mock_db, mock_rag):
        mock_rec = MagicMock()
        mock_rec.id = uuid4()
        _mock_db_execute_scalar_one_or_none(mock_db, mock_rec)
        resp = client.delete(f"/knowledge/urls/{mock_rec.id}")
        assert resp.status_code == 204
        mock_db.delete.assert_called_once_with(mock_rec)
        mock_db.commit.assert_called()
        mock_rag["delete_file"].assert_called_once()

    def test_delete_url_not_found(self, client, mock_db, mock_rag):
        _mock_db_execute_scalar_one_or_none(mock_db, None)
        resp = client.delete(f"/knowledge/urls/{uuid4()}")
        assert resp.status_code == 404

    def test_url_chunks(self, client, mock_db, mock_rag):
        mock_rec = MagicMock()
        mock_rec.id = uuid4()
        _mock_db_execute_scalar_one_or_none(mock_db, mock_rec)
        mock_rag["get_chunks_for_file"].return_value = [
            {"index": 0, "text": "chunk content", "section": "", "char_start": 0, "char_end": 14, "chunk_hash": "abc"},
        ]
        resp = client.get(f"/knowledge/urls/{mock_rec.id}/chunks")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1


@patch("app.knowledge.asyncio.create_task", MagicMock())
class TestImportUrlAuthGuard:
    def test_import_url_requires_auth(self, app):
        app.dependency_overrides.clear()
        with TestClient(app) as c:
            resp = c.post("/knowledge/urls", json={"url": "https://example.com", "title": "Test"})
        assert resp.status_code in (401, 403)

    def test_list_urls_requires_auth(self, app):
        app.dependency_overrides.clear()
        with TestClient(app) as c:
            resp = c.get("/knowledge/urls")
        assert resp.status_code in (401, 403)

    def test_delete_url_requires_auth(self, app):
        app.dependency_overrides.clear()
        with TestClient(app) as c:
            resp = c.delete(f"/knowledge/urls/{uuid4()}")
        assert resp.status_code in (401, 403)


# ── Overview ────────────────────────────────────────────────────────────────


class TestOverview:
    def test_overview_returns_structure(self, client, mock_db, mock_rag):
        """/knowledge/overview returns the expected shape with all keys."""
        mock_db.execute.return_value.scalar.return_value = 0
        resp = client.get("/knowledge/overview")
        assert resp.status_code == 200
        data = resp.json()
        assert "files" in data
        assert "pms" in data
        assert "chunks" in data
        assert "count" in data["files"]
        assert "size_bytes" in data["files"]
        assert "chunks" in data["files"]
        assert "services" in data["pms"]
        assert "practitioners" in data["pms"]
        assert "clinic" in data["pms"]
        assert "chunks" in data["pms"]
        assert "kb" in data["chunks"]
        assert "pms" in data["chunks"]

    def test_overview_with_data(self, client, mock_db, mock_rag):
        """Overview returns correct counts when data exists."""
        def scalar_side_effect():
            counts = [12, 3, 45000, 8, 4, 1]
            return iter(counts).__next__
        mock_db.execute.return_value.scalar.side_effect = [12, 3, 45000, 8, 4, 1]
        resp = client.get("/knowledge/overview")
        assert resp.status_code == 200
        data = resp.json()
        assert data["files"]["count"] == 15
        assert data["files"]["size_bytes"] == 45000
        assert data["pms"]["services"] == 8
        assert data["pms"]["practitioners"] == 4
        assert data["pms"]["clinic"] == 1

    def test_overview_auth_guard(self, app):
        app.dependency_overrides.clear()
        with TestClient(app) as c:
            resp = c.get("/knowledge/overview")
        assert resp.status_code in (401, 403)


# ── Auth guard ──────────────────────────────────────────────────────────────


class TestAuthGuard:
    def test_upload_requires_auth(self, app):
        app.dependency_overrides.clear()
        with TestClient(app) as c:
            resp = c.post("/knowledge/files", files={"file": ("t.txt", io.BytesIO(b"data"), "text/plain")})
        assert resp.status_code in (401, 403)

    def test_list_requires_auth(self, app):
        app.dependency_overrides.clear()
        with TestClient(app) as c:
            resp = c.get("/knowledge/files")
        assert resp.status_code in (401, 403)

    def test_delete_requires_auth(self, app):
        app.dependency_overrides.clear()
        with TestClient(app) as c:
            resp = c.delete(f"/knowledge/files/{uuid4()}")
        assert resp.status_code in (401, 403)

    def test_cleanup_requires_auth(self, app):
        app.dependency_overrides.clear()
        with TestClient(app) as c:
            resp = c.post("/knowledge/cleanup")
        assert resp.status_code in (401, 403)


