"""Integration tests for knowledge.py FastAPI routes.

Uses TestClient with overridden dependencies (auth, db) and
mocked rag/chunking internals.
"""
from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, ANY
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
        "search": MagicMock(return_value=[
            {"text": "chunk1", "score": 0.9, "filename": "doc.txt", "distance": 0.1}
        ]),
        "delete_file": MagicMock(),
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
        from app.chunking import sanitize_filename as real_sf
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


# ── Upload tests ───────────────────────────────────────────────────────────


class TestUploadFile:
    def test_upload_success(self, client, mock_db, mock_rag, mock_chunking, tmp_path):
        mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
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
        mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = fake_rec

        with patch("app.knowledge._settings.knowledge_dir", str(tmp_path)):
            resp = client.post(
                "/knowledge/files",
                files={"file": ("test.txt", io.BytesIO(b"hello world"), "text/plain")},
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["duplicate"] is True

    def test_upload_unsupported_extension(self, client, mock_db, mock_rag, mock_chunking):
        resp = client.post(
            "/knowledge/files",
            files={"file": ("test.exe", io.BytesIO(b"binary data"), "application/octet-stream")},
        )
        assert resp.status_code == 400
        assert "Unsupported" in resp.text

    def test_upload_too_large(self, client, mock_db, mock_rag, mock_chunking, tmp_path):
        mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

        big_data = b"x" * (MAX_SIZE_MB * 1024 * 1024 + 1)
        with patch("app.knowledge._settings.knowledge_dir", str(tmp_path)):
            resp = client.post(
                "/knowledge/files",
                files={"file": ("big.txt", io.BytesIO(big_data), "text/plain")},
            )
        assert resp.status_code == 413

    def test_upload_size_at_limit(self, client, mock_db, mock_rag, mock_chunking, tmp_path):
        mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

        data_at_limit = b"x" * (MAX_SIZE_MB * 1024 * 1024)
        with patch("app.knowledge._settings.knowledge_dir", str(tmp_path)):
            resp = client.post(
                "/knowledge/files",
                files={"file": ("at_limit.txt", io.BytesIO(data_at_limit), "text/plain")},
            )
        assert resp.status_code == 201

    def test_upload_no_filename(self, client, mock_db, mock_rag, mock_chunking, tmp_path):
        mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

        with patch("app.knowledge._settings.knowledge_dir", str(tmp_path)):
            resp = client.post(
                "/knowledge/files",
                files={"file": ("", io.BytesIO(b"data"), "text/plain")},
            )
        # Empty filename → sanitize yields "unnamed"
        assert resp.status_code in (201, 422)

    def test_upload_background_index_called(self, client, mock_db, mock_rag, mock_chunking, tmp_path):
        mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

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
        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []
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
        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [f1, f2]

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

        mock_db.query.return_value.filter.return_value.first.return_value = rec

        resp = client.delete(f"/knowledge/files/{file_id}")
        assert resp.status_code == 204
        mock_db.delete.assert_called_once_with(rec)
        mock_db.commit.assert_called_once()
        mock_rag["delete_file"].assert_called_once()

    def test_delete_not_found(self, client, mock_db, mock_rag):
        mock_db.query.return_value.filter.return_value.first.return_value = None
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

        mock_db.query.return_value.filter.return_value.first.return_value = rec
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

        mock_db.query.return_value.filter.return_value.first.return_value = rec

        resp = client.delete(f"/knowledge/files/{file_id}")
        assert resp.status_code == 204


# ── Chat ───────────────────────────────────────────────────────────────────


class TestChat:
    def test_chat_with_context(self, client, mock_db, mock_rag, mock_openai_chat):
        mock_rag["search"].return_value = [
            {"text": "Relevant context here.", "score": 0.95, "filename": "doc.txt", "distance": 0.05}
        ]

        resp = client.post("/knowledge/chat", json={"message": "What is this about?"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["response"] == "Mocked response."

    def test_chat_without_context(self, client, mock_db, mock_rag, mock_openai_chat):
        mock_rag["search"].return_value = []

        resp = client.post("/knowledge/chat", json={"message": "Tell me something."})
        assert resp.status_code == 200
        data = resp.json()
        assert data["response"] == "Mocked response."

    def test_chat_empty_message(self, client, mock_db, mock_rag, mock_openai_chat):
        mock_rag["search"].return_value = []

        resp = client.post("/knowledge/chat", json={"message": ""})
        assert resp.status_code == 200

    def test_chat_openai_error(self, client, mock_db, mock_rag):
        mock_rag["search"].return_value = []

        with patch("openai.AsyncOpenAI") as mock_oa:
            mock_oa.return_value.chat.completions.create.side_effect = Exception("API error")
            # Exception propagates through middleware as ExceptionGroup;
            # global handler doesn't catch ExceptionGroup.
            with pytest.raises(Exception):
                client.post("/knowledge/chat", json={"message": "Hi"})


# ── Cleanup ────────────────────────────────────────────────────────────────


class TestCleanup:
    def test_cleanup_returns_stats(self, client, mock_db, mock_rag):
        fid = uuid4()
        rec1 = MagicMock()
        rec1.id = fid
        mock_db.query.return_value.filter.return_value.all.return_value = [rec1]
        mock_rag["purge_orphans"].return_value = {"total": 10, "removed": 2}
        mock_rag["deduplicate_collection"].return_value = {"total": 8, "removed": 1}

        resp = client.post("/knowledge/cleanup")
        assert resp.status_code == 200
        data = resp.json()
        assert "purge" in data
        assert "dedup" in data
        mock_rag["purge_orphans"].assert_called_once_with(ANY, {str(fid)})

    def test_cleanup_no_files(self, client, mock_db, mock_rag):
        mock_db.query.return_value.filter.return_value.all.return_value = []
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


# ══════════════════════════════════════════════════════════════════════
# Catalog endpoint tests
# ══════════════════════════════════════════════════════════════════════


@pytest.fixture
def mock_rag_index_products():
    with patch("app.knowledge.rag.index_products", return_value=1) as m:
        yield m


@pytest.fixture
def mock_rag_delete_batch():
    with patch("app.knowledge.rag.delete_products_by_batch", return_value=1) as m:
        yield m


class TestCatalogUpload:
    def test_upload_csv_success(self, client, mock_db, mock_chunking, mock_rag_index_products, tmp_path):
        mock_db.add.return_value = None
        mock_db.commit.return_value = None
        csv_content = b"name,product_id,price,stock_status\nWidget Pro,WP-001,29.99,in_stock"
        with patch("app.knowledge._settings.knowledge_dir", str(tmp_path)):
            resp = client.post(
                "/knowledge/catalog/upload",
                files={"file": ("products.csv", io.BytesIO(csv_content), "text/csv")},
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["imported"] == 1
        assert len(data["errors"]) == 0
        assert "batch_id" in data
        assert data["filename"] == "products.csv"

    def test_upload_json_success(self, client, mock_db, mock_chunking, mock_rag_index_products, tmp_path):
        mock_db.add.return_value = None
        mock_db.commit.return_value = None
        json_content = b'[{"name":"Widget","product_id":"W1","price":19.99}]'
        with patch("app.knowledge._settings.knowledge_dir", str(tmp_path)):
            resp = client.post(
                "/knowledge/catalog/upload",
                files={"file": ("products.json", io.BytesIO(json_content), "application/json")},
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["imported"] == 1

    def test_upload_unsupported_extension(self, client, mock_db, mock_chunking):
        resp = client.post(
            "/knowledge/catalog/upload",
            files={"file": ("products.exe", io.BytesIO(b"data"), "application/octet-stream")},
        )
        assert resp.status_code == 400
        assert "Unsupported" in resp.text

    def test_upload_creates_filerecord(self, client, mock_db, mock_chunking, mock_rag_index_products, tmp_path):
        mock_db.add.return_value = None
        mock_db.commit.return_value = None
        csv_content = b"name,price\nWidget,9.99"
        with patch("app.knowledge._settings.knowledge_dir", str(tmp_path)):
            resp = client.post(
                "/knowledge/catalog/upload",
                files={"file": ("cat.csv", io.BytesIO(csv_content), "text/csv")},
            )
        assert resp.status_code == 201

        # Verify FileRecord was created with correct type
        add_calls = [c for c in mock_db.add.call_args_list if c[0][0].__class__.__name__ == "FileRecord"]
        assert len(add_calls) >= 1
        rec = add_calls[0][0][0]
        assert rec.file_type == "catalog"

    def test_upload_empty_csv(self, client, mock_db, mock_chunking, tmp_path):
        mock_db.add.return_value = None
        mock_db.commit.return_value = None
        with patch("app.knowledge._settings.knowledge_dir", str(tmp_path)):
            resp = client.post(
                "/knowledge/catalog/upload",
                files={"file": ("empty.csv", io.BytesIO(b"name,price\n"), "text/csv")},
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["imported"] == 0
        assert "No products found" in str(data["errors"])

    def test_upload_with_parse_errors(self, client, mock_db, mock_chunking, mock_rag_index_products, tmp_path):
        mock_db.add.return_value = None
        mock_db.commit.return_value = None
        csv_content = b"name,price\n,10.99\nWidget,not_a_number\nGadget,20.99"
        with patch("app.knowledge._settings.knowledge_dir", str(tmp_path)):
            resp = client.post(
                "/knowledge/catalog/upload",
                files={"file": ("partial.csv", io.BytesIO(csv_content), "text/csv")},
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["imported"] == 2  # 2 valid products
        assert len(data["errors"]) == 2  # 2 errors


class TestCatalogList:
    def _build_query_mock(self, result):
        """Build a self-returning query mock chain.
        The endpoint calls: query.filter(a, b) [.filter(c)] .order_by().limit().all()
        """
        q = MagicMock()
        q.filter.return_value = q
        q.order_by.return_value = q
        q.limit.return_value = q
        q.all.return_value = result
        return q

    def test_list_empty(self, client, mock_db, mock_rag):
        mock_db.query.return_value = self._build_query_mock([])
        resp = client.get("/knowledge/catalog")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["results"] == []

    def test_list_with_products(self, client, mock_db, mock_rag):
        from datetime import datetime
        from app.models import ProductCatalog

        p1 = ProductCatalog(
            id=uuid4(), tenant_id=uuid4(), product_id="P1", name="Alpha",
            category="A", price=1999, currency="USD", stock_status="in_stock",
            active=True, import_batch="b1",
            created_at=datetime(2025, 1, 1),
        )
        p2 = ProductCatalog(
            id=uuid4(), tenant_id=uuid4(), product_id="P2", name="Beta",
            category="B", price=2999, currency="USD", stock_status="out_of_stock",
            active=True, import_batch="b1",
            created_at=datetime(2025, 1, 2),
        )

        mock_db.query.return_value = self._build_query_mock([p1, p2])
        resp = client.get("/knowledge/catalog")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert data["results"][0]["name"] == "Alpha"
        assert data["results"][1]["name"] == "Beta"

    def test_list_filter_by_category(self, client, mock_db, mock_rag):
        from app.models import ProductCatalog
        p = ProductCatalog(id=uuid4(), tenant_id=uuid4(), product_id="P1", name="X",
                           category="Electronics", active=True,
                           created_at=__import__("datetime").datetime(2025, 1, 1))
        mock_db.query.return_value = self._build_query_mock([p])

        resp = client.get("/knowledge/catalog?category=Electronics")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    def test_list_filter_by_stock(self, client, mock_db, mock_rag):
        from app.models import ProductCatalog
        p = ProductCatalog(id=uuid4(), tenant_id=uuid4(), product_id="P1", name="X",
                           stock_status="in_stock", active=True,
                           created_at=__import__("datetime").datetime(2025, 1, 1))
        mock_db.query.return_value = self._build_query_mock([p])

        resp = client.get("/knowledge/catalog?in_stock=true")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1


class TestCatalogGetProduct:
    def test_get_existing(self, client, mock_db, mock_rag):
        from datetime import datetime
        from app.models import ProductCatalog

        pid = uuid4()
        p = ProductCatalog(
            id=pid, tenant_id=uuid4(), product_id="P1", name="Widget",
            price=2999, active=True, created_at=datetime(2025, 1, 1),
            updated_at=datetime(2025, 1, 2),
        )
        mock_db.query.return_value.filter.return_value.first.return_value = p

        resp = client.get(f"/knowledge/catalog/{pid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Widget"
        assert data["price"] == 2999

    def test_get_not_found(self, client, mock_db, mock_rag):
        mock_db.query.return_value.filter.return_value.first.return_value = None
        resp = client.get(f"/knowledge/catalog/{uuid4()}")
        assert resp.status_code == 404


class TestCatalogDeleteProduct:
    def test_delete_existing(self, client, mock_db, mock_rag):
        from app.models import ProductCatalog
        pid = uuid4()
        rec = ProductCatalog(id=pid, tenant_id=uuid4(), product_id="P1", name="X", active=True)
        mock_db.query.return_value.filter.return_value.first.return_value = rec

        resp = client.delete(f"/knowledge/catalog/{pid}")
        assert resp.status_code == 204
        assert rec.active is False
        mock_db.commit.assert_called_once()

    def test_delete_not_found(self, client, mock_db, mock_rag):
        mock_db.query.return_value.filter.return_value.first.return_value = None
        resp = client.delete(f"/knowledge/catalog/{uuid4()}")
        assert resp.status_code == 404


class TestCatalogDeleteBatch:
    def test_delete_batch(self, client, mock_db, mock_rag_delete_batch, mock_rag):
        # mock_db.query.return_value... is chained. We need to set up the update mock
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.update.return_value = 3  # 3 rows affected

        resp = client.delete("/knowledge/catalog/batch/my_batch_1")
        assert resp.status_code == 204
        mock_rag_delete_batch.assert_called_once_with(ANY, "my_batch_1")

    def test_delete_nonexistent_batch(self, client, mock_db, mock_rag_delete_batch, mock_rag):
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.update.return_value = 0

        resp = client.delete("/knowledge/catalog/batch/nonexistent")
        assert resp.status_code == 204


class TestCatalogAuthGuard:
    def test_upload_requires_auth(self, app):
        app.dependency_overrides.clear()
        with TestClient(app) as c:
            resp = c.post("/knowledge/catalog/upload", files={"file": ("t.csv", io.BytesIO(b"data"), "text/csv")})
        assert resp.status_code in (401, 403)

    def test_list_requires_auth(self, app):
        app.dependency_overrides.clear()
        with TestClient(app) as c:
            resp = c.get("/knowledge/catalog")
        assert resp.status_code in (401, 403)

    def test_get_requires_auth(self, app):
        app.dependency_overrides.clear()
        with TestClient(app) as c:
            resp = c.get(f"/knowledge/catalog/{uuid4()}")
        assert resp.status_code in (401, 403)

    def test_delete_product_requires_auth(self, app):
        app.dependency_overrides.clear()
        with TestClient(app) as c:
            resp = c.delete(f"/knowledge/catalog/{uuid4()}")
        assert resp.status_code in (401, 403)

    def test_delete_batch_requires_auth(self, app):
        app.dependency_overrides.clear()
        with TestClient(app) as c:
            resp = c.delete("/knowledge/catalog/batch/test")
        assert resp.status_code in (401, 403)
