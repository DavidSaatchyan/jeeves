"""Shared fixtures for knowledge/RAG tests."""
from __future__ import annotations

import os

# Must set env vars BEFORE any app imports to satisfy Settings() validation.
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-fake-key-for-tests")
os.environ.setdefault("JWT_SECRET", "this-is-a-test-secret-that-is-long-enough-32")
os.environ.setdefault("KNOWLEDGE_DIR", str(__file__))

import pytest
from pathlib import Path
from typing import Generator
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import app as _app
from app.models import Tenant
from app.auth import get_current_tenant


@pytest.fixture(autouse=True)
def _patch_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Redirect knowledge_dir to a temp dir for every test."""
    monkeypatch.setattr("app.knowledge._settings.knowledge_dir", str(tmp_path))


@pytest.fixture
def app() -> FastAPI:
    return _app


@pytest.fixture
def tenant_id() -> UUID:
    return uuid4()


@pytest.fixture
def mock_tenant(tenant_id: UUID) -> Tenant:
    t = Tenant(id=tenant_id, name="test", email="test@example.com")
    t.id = tenant_id
    return t


@pytest.fixture
def client(app: FastAPI, mock_tenant: Tenant) -> Generator[TestClient, None, None]:
    def _override_tenant():
        return mock_tenant

    app.dependency_overrides[get_current_tenant] = _override_tenant

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


@pytest.fixture
def sample_txt(tmp_path: Path) -> Path:
    p = tmp_path / "test.txt"
    p.write_text("Hello world. This is a test document. " * 20, encoding="utf-8")
    return p


@pytest.fixture
def sample_md(tmp_path: Path) -> Path:
    p = tmp_path / "test.md"
    p.write_text(
        "# Introduction\n\nThis is the intro.\n\n"
        "# Details\n\nMore details here.\n\n"
        "## Subsection\n\nSub content.\n\n"
        "# Conclusion\n\nWrapping up.",
        encoding="utf-8",
    )
    return p


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    from pypdf import PdfWriter
    p = tmp_path / "test.pdf"
    writer = PdfWriter()
    writer.add_blank_page(612, 792)
    writer.add_blank_page(612, 792)
    writer.write(str(p))
    writer.close()
    return p


# ── Golden dataset fixtures (Sprint 0) ──────────────────────────────────────

_GOLDEN_DATASET_PATH = Path(__file__).parent / "golden_dataset.jsonl"
_SYNTHETIC_KB_DIR = Path(__file__).parent / "synthetic_kb"
_SYNTHETIC_HMS_DIR = Path(__file__).parent / "synthetic_hms"


@pytest.fixture(scope="session")
def golden_dataset() -> list[dict]:
    """Load golden dataset from JSONL."""
    import json
    samples = []
    with open(_GOLDEN_DATASET_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                samples.append(json.loads(line))
    return samples


@pytest.fixture
def synthetic_kb_loader(tenant_id: str):
    """Index synthetic KB docs into Chroma for eval tenant."""
    from app.rag import index_file, delete_file
    loaded: list[str] = []
    for fpath in sorted(_SYNTHETIC_KB_DIR.iterdir()):
        if fpath.suffix not in (".txt", ".md"):
            continue
        fid = f"synthetic-{fpath.stem}"
        try:
            delete_file(tenant_id, fid)
        except Exception:
            pass
        index_file(tenant_id, fid, fpath)
        loaded.append(fid)
    yield loaded
    # Cleanup
    for fid in loaded:
        try:
            delete_file(tenant_id, fid)
        except Exception:
            pass


@pytest.fixture
def synthetic_hms_loader(tenant_id: str):
    """Index synthetic HMS data into Chroma for eval tenant."""
    from app.rag import index_text, delete_file
    loaded: list[str] = []
    for fpath in sorted(_SYNTHETIC_HMS_DIR.iterdir()):
        if fpath.suffix not in (".txt",):
            continue
        fid = f"synthetic-hms-{fpath.stem}"
        try:
            delete_file(tenant_id, fid)
        except Exception:
            pass
        text = fpath.read_text(encoding="utf-8")
        index_text(tenant_id, fid, text, fpath.name, section="Pricing")
        loaded.append(fid)
    yield loaded
    for fid in loaded:
        try:
            delete_file(tenant_id, fid)
        except Exception:
            pass
