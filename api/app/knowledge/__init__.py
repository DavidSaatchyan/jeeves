"""Knowledge Manager routes (FR-2)."""
from __future__ import annotations

import asyncio
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Form, HTTPException, Query, UploadFile, File
from sqlalchemy import select
from sqlalchemy.orm import Session

from pydantic import BaseModel, Field, field_validator

from ..rag.chunking import file_sha256, sanitize_filename

from ..auth.deps import get_current_tenant
from .. import rag
from ..config import get_settings
from ..core.ai.generator import naturalize_answer
from ..db import get_db, engine
from ..models import FileRecord, KbActivity, KnowledgeFolder, KnowledgeUrl, Tenant
from ..schemas import BatchUploadOut, BatchUploadResultItem
from . import sync as _sync

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/knowledge", tags=["knowledge"])
router.include_router(_sync.router, prefix="/sync")



class _ActivityOut(BaseModel):
    id: str
    event_type: str
    description: str
    ref_id: str | None
    created_at: str


@router.get("/activity")
def list_activity(
    limit: int = Query(50, ge=1, le=200),
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(KbActivity)
        .where(KbActivity.tenant_id == tenant.id)
        .order_by(KbActivity.created_at.desc())
        .limit(limit)
    ).scalars().all()
    return [
        _ActivityOut(
            id=str(r.id),
            event_type=r.event_type,
            description=r.description,
            ref_id=r.ref_id,
            created_at=_iso_utc(r.created_at),
        )
        for r in rows
    ]


_settings = get_settings()

MAX_SIZE_MB = 50
ALLOWED_EXT = {".txt", ".pdf", ".md"}


async def _background_index(tenant_id: uuid.UUID, file_id: uuid.UUID, file_path: Path):
    """Run RAG indexing in a background thread to avoid blocking the HTTP request."""
    try:
        logger.info("[index] Starting indexing file %s at %s", file_id, file_path)
        # Read folder_id from DB
        try:
            from sqlalchemy import text as sa_text
            with engine.connect() as conn:
                row = conn.execute(sa_text("SELECT folder_id FROM files WHERE id=:fid"), {"fid": str(file_id)}).fetchone()
                folder_id = str(row[0]) if row and row[0] else ""
        except Exception:
            folder_id = ""
        n = await asyncio.to_thread(rag.index_file, tenant_id, file_id, file_path, folder_id)
        logger.info("[index] Indexed %s chunks for file %s, updating DB", n, file_id)
        with engine.begin() as conn:
            from sqlalchemy import text
            conn.execute(
                text("UPDATE files SET status='ready', chunks_total=:n, error=NULL WHERE id=:fid"),
                {"fid": str(file_id), "n": n},
            )
        logger.info("[index] File %s marked as ready", file_id)
    except Exception as e:
        import traceback
        logger.error("[index] Failed to index file %s: %s", file_id, traceback.format_exc())
        try:
            with engine.begin() as conn:
                from sqlalchemy import text
                conn.execute(
                    text("UPDATE files SET status='failed', error=:error WHERE id=:fid"),
                    {"fid": str(file_id), "error": str(e)[:2000]},
                )
        except Exception as db_err:
            logger.error("[index] Failed to update DB status for %s: %s", file_id, db_err)


def _iso_utc(dt) -> str:
    """Convert naive or aware datetime to UTC ISO string with 'Z' suffix."""
    if dt is None:
        dt = datetime.now(timezone.utc)
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + "Z"


def _tenant_dir(tenant_id: uuid.UUID) -> Path:
    p = Path(_settings.knowledge_dir) / str(tenant_id)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _total_size(tenant_id: uuid.UUID) -> int:
    total = 0
    for root, _, files in os.walk(_tenant_dir(tenant_id)):
        for f in files:
            total += os.path.getsize(os.path.join(root, f))
    return total


def _log_activity(
    db: Session,
    tenant_id: uuid.UUID,
    event_type: str,
    description: str,
    ref_id: str | None = None,
) -> None:
    db.add(KbActivity(tenant_id=tenant_id, event_type=event_type, description=description, ref_id=ref_id))


async def _index_document(
    data: bytes,
    original_filename: str,
    safe_filename: str,
    ext: str,
    folder_id: uuid.UUID | None,
    tenant: Tenant,
    db: Session,
) -> dict:
    """Validate, save, and index a single document.

    Returns a result dict (success or error). Never raises HTTPException.
    Does NOT check total tenant size — caller is responsible for that.
    Does NOT validate folder existence — caller is responsible for that.
    """
    if ext not in ALLOWED_EXT:
        return {"filename": original_filename, "error": f"Unsupported type {ext}. Allowed: {sorted(ALLOWED_EXT)}"}

    content_hash = file_sha256(data)
    duplicate = db.execute(
        select(FileRecord).where(
            FileRecord.tenant_id == tenant.id,
            FileRecord.content_hash == content_hash,
            FileRecord.status != "failed",
        ).order_by(FileRecord.created_at.desc())
    ).scalars().first()
    if duplicate:
        return {
            "id": str(duplicate.id),
            "filename": duplicate.filename,
            "status": duplicate.status,
            "duplicate": True,
        }

    file_id = uuid.uuid4()
    tenant_dir = _tenant_dir(tenant.id) / str(file_id)
    tenant_dir.mkdir(parents=True, exist_ok=True)
    dest = tenant_dir / safe_filename
    dest.write_bytes(data)

    rec = FileRecord(
        id=file_id,
        tenant_id=tenant.id,
        folder_id=folder_id,
        filename=safe_filename,
        s3_key=str(dest),
        status="processing",
        content_hash=content_hash,
        size_bytes=len(data),
    )
    db.add(rec)
    db.commit()
    _log_activity(db, tenant.id, "file_uploaded", f"Uploaded {safe_filename}", str(file_id))
    db.commit()

    asyncio.create_task(_background_index(tenant.id, file_id, dest))
    return {"id": str(file_id), "filename": safe_filename, "status": "processing", "chunks": 0, "folder_id": str(folder_id) if folder_id else None}


@router.post("/files", status_code=201)
async def upload_file(
    file: UploadFile = File(...),
    folder_id: uuid.UUID | None = Form(None),
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    original_filename = file.filename or "unnamed"
    safe_filename = sanitize_filename(original_filename)
    ext = Path(safe_filename).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, f"Unsupported type {ext}. Allowed: {sorted(ALLOWED_EXT)}")

    data = await file.read()
    content_hash = file_sha256(data)
    duplicate = db.execute(
        select(FileRecord).where(
            FileRecord.tenant_id == tenant.id,
            FileRecord.content_hash == content_hash,
            FileRecord.status != "failed",
        ).order_by(FileRecord.created_at.desc())
    ).scalars().first()
    if duplicate:
        return {
            "id": str(duplicate.id),
            "status": duplicate.status,
            "duplicate": True,
            "filename": duplicate.filename,
        }

    file_id = uuid.uuid4()
    tenant_dir = _tenant_dir(tenant.id) / str(file_id)
    tenant_dir.mkdir(parents=True, exist_ok=True)
    dest = tenant_dir / safe_filename

    if _total_size(tenant.id) + len(data) > MAX_SIZE_MB * 1024 * 1024:
        raise HTTPException(413, f"Total knowledge size would exceed {MAX_SIZE_MB} MB")

    if folder_id:
        folder = db.execute(select(KnowledgeFolder).where(
            KnowledgeFolder.id == folder_id,
            KnowledgeFolder.tenant_id == tenant.id,
        )).scalar_one_or_none()
        if not folder:
            raise HTTPException(404, "folder not found")

    dest.write_bytes(data)

    rec = FileRecord(
        id=file_id,
        tenant_id=tenant.id,
        folder_id=folder_id,
        filename=safe_filename,
        s3_key=str(dest),
        status="processing",
        content_hash=content_hash,
        size_bytes=len(data),
    )
    db.add(rec)
    db.commit()
    _log_activity(db, tenant.id, "file_uploaded", f"Uploaded {safe_filename}", str(file_id))
    db.commit()

    # Index asynchronously in background thread
    asyncio.create_task(_background_index(tenant.id, file_id, dest))
    return {"id": str(file_id), "status": "processing", "chunks": 0, "folder_id": str(folder_id) if folder_id else None}


@router.post("/files/batch", status_code=201)
async def upload_files_batch(
    files: list[UploadFile] = File(default=[]),
    folder_id: uuid.UUID | None = Form(None),
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    if not files:
        return BatchUploadOut(results=[])

    if folder_id:
        folder = db.execute(select(KnowledgeFolder).where(
            KnowledgeFolder.id == folder_id,
            KnowledgeFolder.tenant_id == tenant.id,
        )).scalar_one_or_none()
        if not folder:
            raise HTTPException(404, "folder not found")

    total_new_size = 0
    entries: list[tuple[bytes, str, str, str]] = []  # (data, original_name, safe_name, ext)
    for f in files:
        data = await f.read()
        original = f.filename or "unnamed"
        safe = sanitize_filename(original)
        ext = Path(safe).suffix.lower()
        entries.append((data, original, safe, ext))
        total_new_size += len(data)

    if _total_size(tenant.id) + total_new_size > MAX_SIZE_MB * 1024 * 1024:
        raise HTTPException(413, f"Total knowledge size would exceed {MAX_SIZE_MB} MB")

    results: list[dict] = []
    for data, original, safe, ext in entries:
        result = await _index_document(data, original, safe, ext, folder_id, tenant, db)
        results.append(result)

    return BatchUploadOut(results=[BatchUploadResultItem(**r) for r in results])


def _is_non_uuid(s: str) -> bool:
    try:
        uuid.UUID(s)
        return False
    except Exception:
        return True


class _SimulateIn(BaseModel):
    query: str
    top_k: int = 5


@router.post("/simulate")
async def simulate(
    body: _SimulateIn,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    if not body.query.strip():
        raise HTTPException(400, "query is required")

    raw = await asyncio.to_thread(rag.search, tenant.id, body.query, top_k=body.top_k)

    # Filter out orphan chunks whose file_id no longer exists in DB
    # Synthetic file_ids (HMS, non-UUID) are kept — they have no DB record.
    file_ids = [r["file_id"] for r in raw if r.get("file_id")]
    if file_ids:
        uuids = []
        for f in file_ids:
            try:
                uuids.append(uuid.UUID(f))
            except Exception:
                pass
        existing = set()
        if uuids:
            for row in db.execute(select(FileRecord.id).where(
                FileRecord.id.in_(uuids),
                FileRecord.tenant_id == tenant.id,
            )).all():
                existing.add(str(row[0]))
            for row in db.execute(select(KnowledgeUrl.id).where(
                KnowledgeUrl.id.in_(uuids),
                KnowledgeUrl.tenant_id == tenant.id,
            )).all():
                existing.add(str(row[0]))
        results = [
            r for r in raw
            if not r.get("file_id")
            or r["file_id"] in existing
            or _is_non_uuid(r["file_id"])
        ]
        if len(results) < len(raw):
            logger.info("simulate: filtered %d orphan chunks from search results", len(raw) - len(results))
    else:
        results = raw

    if results:
        blocks = []
        for i, r in enumerate(results, 1):
            source = r.get("filename", "?")
            section = r.get("section", "") or ""
            sect_label = f" — Section: \"{section}\"" if section else ""
            sep = "═" * 60
            blocks.append(
                f"[Document {i}] {source}{sect_label}\n"
                f"{sep}\n"
                f"{r['text']}\n"
                f"{sep}"
            )
        context = "\n\n".join(blocks)

        system_prompt = (
            "You are an extractive knowledge base system.\n\n"
            "RULES:\n"
            "- Answer ONLY using text that appears verbatim in the context below.\n"
            "- For every claim, quote the exact source text in quotation marks and cite the document.\n"
            "- If the context does not contain the answer, say: \"I don't have this information in the knowledge base.\"\n"
            "- Do NOT combine separate facts into causal or sequential relationships unless the source text explicitly states that relationship.\n"
            "- Do NOT use your training knowledge to supplement or interpret the context.\n\n"
            "CONTEXT:\n" + context
        )
    else:
        system_prompt = (
            "You are an extractive knowledge base system. "
            "No relevant documents were found for the query. "
            "State that this information is not present in the knowledge base. Do not guess or make up an answer."
        )

    from ..schemas import KBResponse
    from ..core.ai.generator import call_structured, deterministic_naturalize

    kb_result = await call_structured(str(tenant.id), system_prompt, body.query, KBResponse, temperature=0.0)

    if kb_result is None:
        answer = "I don't have this information in the knowledge base."
    else:
        answer = deterministic_naturalize(kb_result) or "I don't have this information in the knowledge base."
        if answer:
            answer = await naturalize_answer(str(tenant.id), answer)

    sources = [
        {"chunk": r["text"][:500], "filename": r["filename"], "section": r["section"], "score": r["score"], "file_id": r.get("file_id", "")}
        for r in results
    ]

    return {"answer": answer, "sources": sources}


@router.get("/files")
def list_files(
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    rows = db.execute(select(FileRecord).where(FileRecord.tenant_id == tenant.id, FileRecord.file_type == "document").order_by(FileRecord.created_at.desc())).scalars().all()
    return [
        {
            "id": str(r.id),
            "filename": r.filename,
            "status": r.status,
            "size_bytes": r.size_bytes or 0,
            "chunks_total": r.chunks_total or 0,
            "created_at": _iso_utc(r.created_at),
            "error": r.error,
            "folder_id": str(r.folder_id) if r.folder_id else None,
        }
        for r in rows
    ]


@router.delete("/files/{file_id}", status_code=204)
def delete_file(
    file_id: uuid.UUID,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    rec = db.execute(select(FileRecord).where(FileRecord.id == file_id, FileRecord.tenant_id == tenant.id)).scalar_one_or_none()
    if not rec:
        raise HTTPException(404, "file not found")

    logger.info("delete: file_id=%s filename=%s tenant=%s", file_id, rec.filename, tenant.id)

    # Remove physical file first (fast)
    file_path = rec.s3_key
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception:
            pass

    # Delete DB record
    db.delete(rec)
    db.commit()
    _log_activity(db, tenant.id, "file_deleted", f"Deleted {rec.filename}", str(file_id))
    db.commit()

    # Delete from Chroma (can be slow, do after DB commit so user sees it gone)
    try:
        rag.delete_file(tenant.id, file_id)
    except Exception as e:
        logger.warning("chroma delete warning: %s", e)

    # Clean up orphan chunks whose file_id no longer exists in DB
    try:
        _cleanup_orphans_after_delete(tenant, db)
    except Exception as e:
        logger.warning("orphan cleanup warning: %s", e)

    return


def _cleanup_orphans_after_delete(tenant: Tenant, db: Session) -> dict:
    """Quick orphan cleanup after a file/URL deletion. Collects active IDs and purges."""
    active: set[str] = set()
    for r in db.execute(select(FileRecord).where(FileRecord.tenant_id == tenant.id)).scalars().all():
        active.add(str(r.id))
    for r in db.execute(select(KnowledgeUrl).where(KnowledgeUrl.tenant_id == tenant.id)).scalars().all():
        active.add(str(r.id))
    p = rag.purge_orphans(tenant.id, active)
    d = rag.deduplicate_collection(tenant.id)
    if p.get("removed", 0) or d.get("removed", 0):
        logger.info("cleanup after delete: purged %d orphans, deduped %d duplicates", p.get("removed", 0), d.get("removed", 0))
    return {"purge": p, "dedup": d}


@router.post("/cleanup")
def cleanup_chroma(
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    """Remove stale/duplicate chunks from Chroma. Steps:
    1. Purge chunks whose file_id no longer exists in DB (orphans)
    2. Deduplicate remaining chunks by (filename, chunk_hash)
    """
    return _cleanup_orphans_after_delete(tenant, db)


# ── Folder CRUD ──────────────────────────────────────────────────────────────


class _FolderCreate(BaseModel):
    name: str
    parent_id: uuid.UUID | None = None


class _FolderUpdate(BaseModel):
    name: str | None = None
    sort_order: int | None = None


@router.get("/folders")
def list_folders(
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(KnowledgeFolder)
        .where(KnowledgeFolder.tenant_id == tenant.id)
        .order_by(KnowledgeFolder.sort_order, KnowledgeFolder.name)
    ).scalars().all()
    return [
        {
            "id": str(r.id),
            "name": r.name,
            "parent_id": str(r.parent_id) if r.parent_id else None,
            "sort_order": r.sort_order or 0,
        }
        for r in rows
    ]


@router.post("/folders", status_code=201)
def create_folder(
    body: _FolderCreate,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    if body.parent_id:
        parent = db.execute(select(KnowledgeFolder).where(
            KnowledgeFolder.id == body.parent_id,
            KnowledgeFolder.tenant_id == tenant.id,
        )).scalar_one_or_none()
        if not parent:
            raise HTTPException(404, "parent folder not found")

    existing = db.execute(select(KnowledgeFolder).where(
        KnowledgeFolder.tenant_id == tenant.id,
        KnowledgeFolder.name == body.name,
        KnowledgeFolder.parent_id == body.parent_id,
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(409, "folder with same name already exists in this location")

    f = KnowledgeFolder(tenant_id=tenant.id, name=body.name, parent_id=body.parent_id)
    db.add(f)
    db.commit()
    _log_activity(db, tenant.id, "folder_created", f"Created folder {body.name}", str(f.id))
    db.commit()
    return {"id": str(f.id), "name": f.name, "parent_id": str(f.parent_id) if f.parent_id else None}


@router.patch("/folders/{folder_id}")
def update_folder(
    folder_id: uuid.UUID,
    body: _FolderUpdate,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    f = db.execute(select(KnowledgeFolder).where(
        KnowledgeFolder.id == folder_id, KnowledgeFolder.tenant_id == tenant.id,
    )).scalar_one_or_none()
    if not f:
        raise HTTPException(404, "folder not found")
    if body.name is not None:
        f.name = body.name
    if body.sort_order is not None:
        f.sort_order = body.sort_order
    db.commit()
    return {"id": str(f.id), "name": f.name}


@router.delete("/folders/{folder_id}", status_code=204)
def delete_folder(
    folder_id: uuid.UUID,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    f = db.execute(select(KnowledgeFolder).where(
        KnowledgeFolder.id == folder_id, KnowledgeFolder.tenant_id == tenant.id,
    )).scalar_one_or_none()
    if not f:
        raise HTTPException(404, "folder not found")
    db.delete(f)
    db.commit()
    _log_activity(db, tenant.id, "folder_deleted", f"Deleted folder {f.name}", str(folder_id))
    db.commit()


# ── File-to-folder assignment ─────────────────────────────────────────────────


class _FileMove(BaseModel):
    folder_id: uuid.UUID | None = None


@router.put("/files/{file_id}/folder")
def move_file(
    file_id: uuid.UUID,
    body: _FileMove,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    rec = db.execute(select(FileRecord).where(
        FileRecord.id == file_id, FileRecord.tenant_id == tenant.id,
    )).scalar_one_or_none()
    if not rec:
        raise HTTPException(404, "file not found")
    if body.folder_id:
        folder = db.execute(select(KnowledgeFolder).where(
            KnowledgeFolder.id == body.folder_id, KnowledgeFolder.tenant_id == tenant.id,
        )).scalar_one_or_none()
        if not folder:
            raise HTTPException(404, "folder not found")
    rec.folder_id = body.folder_id
    db.commit()
    return {"id": str(rec.id), "folder_id": str(rec.folder_id) if rec.folder_id else None}


# ── File content ─────────────────────────────────────────────────────────────


_TXT_EXT = {".txt", ".md"}


@router.get("/files/{file_id}/content")
def get_file_content(
    file_id: uuid.UUID,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    rec = db.execute(select(FileRecord).where(
        FileRecord.id == file_id, FileRecord.tenant_id == tenant.id,
    )).scalar_one_or_none()
    if not rec:
        raise HTTPException(404, "file not found")

    ext = Path(rec.filename).suffix.lower()
    if ext not in _TXT_EXT:
        raise HTTPException(400, f"Cannot display content for {ext} files inline")

    file_path = Path(rec.s3_key) if rec.s3_key else None
    if not file_path or not file_path.exists():
        content = ""
    else:
        content = file_path.read_text(encoding="utf-8")

    return {"filename": rec.filename, "content": content}


class _ContentUpdate(BaseModel):
    content: str


@router.put("/files/{file_id}/content")
async def update_file_content(
    file_id: uuid.UUID,
    body: _ContentUpdate,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    rec = db.execute(select(FileRecord).where(
        FileRecord.id == file_id, FileRecord.tenant_id == tenant.id,
    )).scalar_one_or_none()
    if not rec:
        raise HTTPException(404, "file not found")

    ext = Path(rec.filename).suffix.lower()
    if ext not in _TXT_EXT:
        raise HTTPException(400, f"Cannot edit {ext} files")

    file_path = Path(rec.s3_key) if rec.s3_key else None
    if not file_path:
        raise HTTPException(404, "file path not found")

    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(body.content, encoding="utf-8")

    # Re-index: delete old chunks, re-index with folder_id preserved
    try:
        rag.delete_file(tenant.id, file_id)
    except Exception:
        pass

    folder_id = str(rec.folder_id) if rec.folder_id else ""
    n = await asyncio.to_thread(rag.index_file, tenant.id, file_id, file_path, folder_id)
    rec.status = "ready"
    rec.chunks_total = n
    db.commit()

    return {"id": str(file_id), "chunks": n}


# ── File chunks ──────────────────────────────────────────────────────────────


@router.get("/files/{file_id}/chunks")
def list_file_chunks(
    file_id: uuid.UUID,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    rec = db.execute(select(FileRecord).where(
        FileRecord.id == file_id, FileRecord.tenant_id == tenant.id,
    )).scalar_one_or_none()
    if not rec:
        raise HTTPException(404, "file not found")

    chunks = rag.get_chunks_for_file(tenant.id, file_id)
    return {"chunks": chunks, "total": len(chunks)}


# ── URL import ────────────────────────────────────────────────────────────────


async def _background_index_url(tenant_id: uuid.UUID, url_id: uuid.UUID, url: str | None, title: str | None):
    """Fetch URL, extract structured sections, index into Chroma in background thread."""
    try:
        from .url_extractor import fetch_url_structured
        logger.info("[url-index] Fetching URL %s for url_id %s", url, url_id)
        resolved_title, sections = await fetch_url_structured(url or "")
        display_name = (title or resolved_title or url or "untitled").strip()
        total_len = sum(len(body) for _, body in sections)
        # Compute content hash for staleness detection
        all_text = "".join(body for _, body in sections)
        import hashlib
        content_hash = hashlib.sha256(all_text.encode()).hexdigest()
        # Read folder_id from DB
        try:
            from sqlalchemy import text as sa_text2
            with engine.connect() as conn:
                row = conn.execute(sa_text2("SELECT folder_id FROM knowledge_urls WHERE id=:uid"), {"uid": str(url_id)}).fetchone()
                folder_id = str(row[0]) if row and row[0] else ""
        except Exception:
            folder_id = ""
        n = await asyncio.to_thread(rag.index_structured_text, tenant_id, url_id, sections, display_name, folder_id)
        logger.info("[url-index] Indexed %s chunks for url %s, updating DB", n, url_id)
        with engine.begin() as conn:
            from sqlalchemy import text as sa_text3
            conn.execute(
                sa_text3("UPDATE knowledge_urls SET status='ready', chunks_total=:n, size_bytes=:sz, content_hash=:ch, last_fetched_at=:lfa, error=NULL WHERE id=:uid"),
                {"uid": str(url_id), "n": n, "sz": total_len, "ch": content_hash, "lfa": datetime.now(timezone.utc)},
            )
        logger.info("[url-index] URL %s marked as ready", url_id)
    except Exception as e:
        import traceback
        logger.error("[url-index] Failed to index URL %s: %s", url_id, traceback.format_exc())
        try:
            with engine.begin() as conn:
                from sqlalchemy import text
                conn.execute(
                    text("UPDATE knowledge_urls SET status='failed', error=:error WHERE id=:uid"),
                    {"uid": str(url_id), "error": str(e)[:2000]},
                )
        except Exception as db_err:
            logger.error("[url-index] Failed to update DB status for %s: %s", url_id, db_err)


def _normalize_url(url: str) -> str:
    return url.strip().lower().rstrip("/")


class _UrlImportIn(BaseModel):
    url: str = Field(max_length=2048)
    title: str | None = Field(None, max_length=512)
    folder_id: uuid.UUID | None = None

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("URL is required")
        if len(v) > 2048:
            raise ValueError("URL must not exceed 2048 characters")
        if not re.match(r"https?://", v, re.IGNORECASE):
            raise ValueError("URL must start with http:// or https://")
        parsed = urlparse(v)
        if not parsed.netloc:
            raise ValueError("Invalid URL: missing hostname")
        return v.strip()


@router.post("/urls", status_code=201)
async def import_url(
    body: _UrlImportIn,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):

    resolved_title = (body.title or body.url).strip()

    if body.folder_id:
        folder = db.execute(select(KnowledgeFolder).where(
            KnowledgeFolder.id == body.folder_id,
            KnowledgeFolder.tenant_id == tenant.id,
        )).scalar_one_or_none()
        if not folder:
            raise HTTPException(404, "folder not found")

    existing = db.execute(
        select(KnowledgeUrl).where(
            KnowledgeUrl.tenant_id == tenant.id,
            KnowledgeUrl.status != "failed",
        )
    ).scalars().all()
    existing = next((r for r in existing if _normalize_url(r.url) == _normalize_url(body.url)), None)
    if existing:
        return {
            "id": str(existing.id),
            "url": existing.url,
            "title": existing.title,
            "status": existing.status,
            "duplicate": True,
        }

    rec = KnowledgeUrl(
        tenant_id=tenant.id,
        url=body.url,
        title=resolved_title,
        folder_id=body.folder_id,
        status="processing",
    )
    db.add(rec)
    db.commit()
    _log_activity(db, tenant.id, "url_imported", f"Imported URL {body.url}", str(rec.id))
    db.commit()

    asyncio.create_task(_background_index_url(tenant.id, rec.id, body.url, resolved_title))
    return {"id": str(rec.id), "url": rec.url, "title": rec.title, "status": rec.status}


class _UrlUpdateBody(BaseModel):
    url: str | None = Field(None, max_length=2048)
    title: str | None = Field(None, max_length=512)

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("URL is required")
        if len(v) > 2048:
            raise ValueError("URL must not exceed 2048 characters")
        if not re.match(r"https?://", v, re.IGNORECASE):
            raise ValueError("URL must start with http:// or https://")
        parsed = urlparse(v)
        if not parsed.netloc:
            raise ValueError("Invalid URL: missing hostname")
        return v


@router.patch("/urls/{url_id}")
def update_url(
    url_id: uuid.UUID,
    body: _UrlUpdateBody,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    rec = db.execute(
        select(KnowledgeUrl).where(
            KnowledgeUrl.id == url_id,
            KnowledgeUrl.tenant_id == tenant.id,
        )
    ).scalar_one_or_none()
    if not rec:
        raise HTTPException(404, "url not found")

    changed = False
    if body.url is not None and body.url != rec.url:
        rec.url = body.url
        changed = True
    if body.title is not None and body.title != rec.title:
        rec.title = body.title

    db.commit()

    if changed:
        asyncio.create_task(_background_index_url(tenant.id, rec.id, rec.url, rec.title))

    return {"ok": True, "changed": changed}


@router.get("/urls")
def list_urls(
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(KnowledgeUrl)
        .where(KnowledgeUrl.tenant_id == tenant.id)
        .order_by(KnowledgeUrl.created_at.desc())
    ).scalars().all()
    return [
        {
            "id": str(r.id),
            "url": r.url,
            "title": r.title,
            "status": r.status,
            "folder_id": str(r.folder_id) if r.folder_id else None,
            "chunks_total": r.chunks_total or 0,
            "size_bytes": r.size_bytes or 0,
            "content_hash": r.content_hash or "",
            "error": r.error,
            "created_at": _iso_utc(r.created_at),
            "last_fetched_at": _iso_utc(r.last_fetched_at) if r.last_fetched_at else None,
        }
        for r in rows
    ]


@router.get("/urls/{url_id}/chunks")
def list_url_chunks(
    url_id: uuid.UUID,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    rec = db.execute(select(KnowledgeUrl).where(
        KnowledgeUrl.id == url_id, KnowledgeUrl.tenant_id == tenant.id,
    )).scalar_one_or_none()
    if not rec:
        raise HTTPException(404, "url not found")
    chunks = rag.get_chunks_for_file(tenant.id, url_id)
    return {"chunks": chunks, "total": len(chunks)}


@router.delete("/urls/{url_id}", status_code=204)
def delete_url(
    url_id: uuid.UUID,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    rec = db.execute(select(KnowledgeUrl).where(
        KnowledgeUrl.id == url_id, KnowledgeUrl.tenant_id == tenant.id,
    )).scalar_one_or_none()
    if not rec:
        raise HTTPException(404, "url not found")

    try:
        rag.delete_file(tenant.id, url_id)
    except Exception:
        pass

    db.delete(rec)
    db.commit()
    _log_activity(db, tenant.id, "url_deleted", f"Deleted URL {rec.url}", str(url_id))
    db.commit()

    try:
        _cleanup_orphans_after_delete(tenant, db)
    except Exception as e:
        logger.warning("orphan cleanup warning: %s", e)


@router.get("/urls/stale")
def list_stale_urls(
    max_age_hours: int = Query(72, ge=1),
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    """Return URLs that haven't been refreshed within max_age_hours."""
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    rows = db.execute(
        select(KnowledgeUrl)
        .where(
            KnowledgeUrl.tenant_id == tenant.id,
            KnowledgeUrl.status == "ready",
            KnowledgeUrl.last_fetched_at < cutoff,
        )
        .order_by(KnowledgeUrl.last_fetched_at.asc().nullsfirst())
    ).scalars().all()
    return [
        {
            "id": str(r.id),
            "url": r.url,
            "title": r.title,
            "last_fetched_at": _iso_utc(r.last_fetched_at) if r.last_fetched_at else None,
            "stale_hours": round((datetime.now(timezone.utc) - (r.last_fetched_at or datetime.now(timezone.utc))).total_seconds() / 3600, 1),
        }
        for r in rows
    ]


@router.post("/urls/{url_id}/refresh")
async def refresh_url(
    url_id: uuid.UUID,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    """Re-fetch URL content and re-index if content has changed.

    Returns whether the content was stale and re-indexed.
    """
    rec = db.execute(select(KnowledgeUrl).where(
        KnowledgeUrl.id == url_id, KnowledgeUrl.tenant_id == tenant.id,
    )).scalar_one_or_none()
    if not rec:
        raise HTTPException(404, "url not found")

    from .url_extractor import fetch_url_structured
    import hashlib

    try:
        resolved_title, sections = await fetch_url_structured(rec.url or "")
        all_text = "".join(body for _, body in sections)
        current_hash = hashlib.sha256(all_text.encode()).hexdigest()
    except Exception as e:
        raise HTTPException(502, f"Failed to fetch URL: {e}")

    if current_hash == rec.content_hash:
        rec.last_fetched_at = datetime.now(timezone.utc)
        db.commit()
        return {"refreshed": False, "message": "Content unchanged"}

    # Content changed — re-index
    try:
        rag.delete_file(tenant.id, url_id)
    except Exception:
        pass

    display_name = (rec.title or resolved_title or rec.url or "untitled").strip()
    total_len = sum(len(body) for _, body in sections)
    n = await asyncio.to_thread(rag.index_structured_text, tenant.id, url_id, sections, display_name)

    rec.status = "ready"
    rec.chunks_total = n
    rec.size_bytes = total_len
    rec.content_hash = current_hash
    rec.last_fetched_at = datetime.now(timezone.utc)
    rec.error = None
    db.commit()

    return {"refreshed": True, "chunks": n, "size_bytes": total_len}


@router.post("/urls/refresh-stale")
def refresh_all_stale_urls(
    max_age_hours: int = Query(72, ge=1),
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    """Refresh all stale URLs for this tenant with concurrency limit of 5."""
    from datetime import timedelta

    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    stale = db.execute(
        select(KnowledgeUrl).where(
            KnowledgeUrl.tenant_id == tenant.id,
            KnowledgeUrl.status == "ready",
            KnowledgeUrl.last_fetched_at < cutoff,
        )
    ).scalars().all()

    sem = asyncio.Semaphore(5)

    async def _refresh_one(url: KnowledgeUrl) -> None:
        async with sem:
            await _background_index_url(tenant.id, url.id, url.url, url.title)

    for url in stale:
        url.status = "processing"
    db.commit()

    for url in stale:
        asyncio.create_task(_refresh_one(url))

    return {"refreshed": len(stale)}


# ── CRM sync is now in knowledge/sync.py (included via router.include_router) ──
