"""Knowledge Manager routes (FR-2)."""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from pydantic import BaseModel

from .chunking import file_sha256, sanitize_filename
from .auth import get_current_tenant
from . import rag
from .config import get_settings
from .db import get_db, engine
from .models import FileRecord, Tenant

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

_settings = get_settings()

MAX_SIZE_MB = 50
ALLOWED_EXT = {".txt", ".pdf", ".md"}


async def _background_index(tenant_id: uuid.UUID, file_id: uuid.UUID, file_path: Path):
    """Run RAG indexing in a background thread to avoid blocking the HTTP request."""
    import logging
    try:
        logging.info("[index] Starting indexing file %s at %s", file_id, file_path)
        n = await asyncio.to_thread(rag.index_file, tenant_id, file_id, file_path)
        logging.info("[index] Indexed %s chunks for file %s, updating DB", n, file_id)
        with engine.begin() as conn:
            from sqlalchemy import text
            conn.execute(
                text("UPDATE files SET status='ready', chunks_total=:n, error=NULL WHERE id=:fid"),
                {"fid": str(file_id), "n": n},
            )
        logging.info("[index] File %s marked as ready", file_id)
    except Exception as e:
        import traceback
        logging.error("[index] Failed to index file %s: %s", file_id, traceback.format_exc())
        try:
            with engine.begin() as conn:
                from sqlalchemy import text
                conn.execute(
                    text("UPDATE files SET status='failed', error=:error WHERE id=:fid"),
                    {"fid": str(file_id), "error": str(e)[:2000]},
                )
        except Exception as db_err:
            logging.error("[index] Failed to update DB status for %s: %s", file_id, db_err)


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


@router.post("/files", status_code=201)
async def upload_file(
    file: UploadFile = File(...),
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
    duplicate = (
        db.query(FileRecord)
        .filter(
            FileRecord.tenant_id == tenant.id,
            FileRecord.content_hash == content_hash,
            FileRecord.status != "failed",
        )
        .order_by(FileRecord.created_at.desc())
        .first()
    )
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

    dest.write_bytes(data)

    rec = FileRecord(
        id=file_id,
        tenant_id=tenant.id,
        filename=safe_filename,
        s3_key=str(dest),
        status="processing",
        content_hash=content_hash,
        size_bytes=len(data),
    )
    db.add(rec)
    db.commit()

    # Index asynchronously in background thread
    asyncio.create_task(_background_index(tenant.id, file_id, dest))
    return {"id": str(file_id), "status": "processing", "chunks": 0}


class _ChatIn(BaseModel):
    message: str


@router.post("/chat")
async def chat(
    body: _ChatIn,
    tenant: Tenant = Depends(get_current_tenant),
):
    from . import rag
    from openai import AsyncOpenAI

    import asyncio
    chunks = await asyncio.to_thread(rag.search, tenant.id, body.message)
    context = "\n\n".join(c["text"] for c in chunks) if chunks else ""

    if context:
        system = f"You are a support agent. Answer the user's question using ONLY the context below. If the context doesn't contain the answer, say you don't know.\n\nContext:\n{context}"
    else:
        system = "You are a support agent. Answer the user's question to the best of your ability."

    client = AsyncOpenAI(api_key=_settings.openai_api_key)
    resp = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": system}, {"role": "user", "content": body.message}],
        temperature=0.3,
        max_tokens=1000,
    )
    return {"response": resp.choices[0].message.content or ""}


@router.get("/files")
def list_files(
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    rows = db.query(FileRecord).filter(FileRecord.tenant_id == tenant.id).order_by(FileRecord.created_at.desc()).all()
    return [
        {
            "id": str(r.id),
            "filename": r.filename,
            "status": r.status,
            "size_bytes": r.size_bytes or 0,
            "chunks_total": r.chunks_total or 0,
            "created_at": _iso_utc(r.created_at),
            "error": r.error,
        }
        for r in rows
    ]


@router.delete("/files/{file_id}", status_code=204)
def delete_file(
    file_id: uuid.UUID,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    rec = db.query(FileRecord).filter(FileRecord.id == file_id, FileRecord.tenant_id == tenant.id).first()
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

    # Delete from Chroma (can be slow, do after DB commit so user sees it gone)
    try:
        rag.delete_file(tenant.id, file_id)
    except Exception as e:
        logger.warning("chroma delete warning: %s", e)

    return


@router.post("/cleanup")
def cleanup_chroma(
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    """Remove stale/duplicate chunks from Chroma. Steps:
    1. Purge chunks whose file_id no longer exists in DB (orphans)
    2. Deduplicate remaining chunks by (filename, chunk_hash)
    """
    active = set()
    for r in db.query(FileRecord).filter(FileRecord.tenant_id == tenant.id).all():
        active.add(str(r.id))

    p = rag.purge_orphans(tenant.id, active)
    d = rag.deduplicate_collection(tenant.id)

    return {"purge": p, "dedup": d}
