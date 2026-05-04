"""Knowledge Manager routes (FR-2)."""
from __future__ import annotations

import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from . import rag
from .chunking import file_sha256, sanitize_filename
from .auth import get_current_tenant
from .config import get_settings
from .db import get_db
from .models import FileRecord, Tenant

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

_settings = get_settings()

_has_redis = bool(_settings.redis_url)
if _has_redis:
    from celery import Celery
    _celery = Celery("jeeves", broker=_settings.redis_url, backend=_settings.redis_url)
else:
    _celery = None

MAX_SIZE_MB = 50
ALLOWED_EXT = {".txt", ".pdf", ".md"}


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

    # Always index synchronously — no Celery dependency
    try:
        n = rag.index_file(tenant.id, file_id, dest)
        rec.status = "ready"
        rec.chunks_total = n
        db.commit()
        return {"id": str(file_id), "status": "ready", "chunks": n}
    except Exception as e:
        rec.status = "failed"
        rec.error = str(e)
        db.commit()
        raise HTTPException(500, f"Indexing failed: {e}")


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
            "created_at": (r.created_at.isoformat() + 'Z') if r.created_at else None,
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

    print(f"[knowledge] deleting file {file_id} ({rec.filename}) for tenant {tenant.id}", flush=True)

    # Delete from Chroma
    rag.delete_file(tenant.id, file_id)

    # Verify deletion
    remaining = rag._count_all_chunks(tenant.id)
    print(f"[knowledge] after delete: {remaining} chunks remain in Chroma", flush=True)

    try:
        if rec.s3_key and os.path.exists(rec.s3_key):
            os.remove(rec.s3_key)
    except Exception:
        pass
    db.delete(rec)
    db.commit()
    return
