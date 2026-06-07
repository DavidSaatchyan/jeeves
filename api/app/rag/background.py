"""Background indexing tasks — extracted from knowledge API for transactional safety."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from uuid import UUID

from ..db import engine

logger = logging.getLogger("jeeves.rag.background")


async def index_file_background(tenant_id: UUID, file_id: UUID, file_path: Path) -> None:
    """Index a file into Chroma, then update the DB record transactionally.

    Guarantees: file is either indexed (chunks in Chroma + status='ready')
    or explicitly marked as ``failed``.  If the DB update fails after a
    successful Chroma index the file is still considered indexed (orphan
    cleanup handles any inconsistency).
    """
    from .. import rag as _rag

    try:
        n = await asyncio.to_thread(_rag.index_file, tenant_id, file_id, file_path)
    except Exception as exc:
        logger.error("index_file_background: index failed for %s: %s", file_id, exc)
        _mark_failed(file_id, exc)
        return

    try:
        with engine.begin() as conn:
            from sqlalchemy import text
            conn.execute(
                text("UPDATE files SET status='ready', chunks_total=:n, error=NULL WHERE id=:fid"),
                {"fid": str(file_id), "n": n},
            )
    except Exception as exc:
        logger.error("index_file_background: DB update failed for %s: %s", file_id, exc)


async def index_url_background(tenant_id: UUID, url_id: UUID, url: str | None, title: str | None) -> None:
    """Fetch a URL, index its content into Chroma, then update DB transactionally."""
    from .. import rag as _rag

    try:
        from .url_extractor import fetch_url_structured
        resolved_title, sections = await fetch_url_structured(url or "")
        display_name = (title or resolved_title or url or "untitled").strip()
        total_len = sum(len(body) for _, body in sections)
        n = await asyncio.to_thread(_rag.index_structured_text, tenant_id, url_id, sections, display_name)
    except Exception as exc:
        logger.error("index_url_background: index failed for %s: %s", url_id, exc)
        _mark_url_failed(url_id, exc)
        return

    try:
        with engine.begin() as conn:
            from sqlalchemy import text
            conn.execute(
                text("UPDATE knowledge_urls SET status='ready', chunks_total=:n, size_bytes=:sz, error=NULL WHERE id=:uid"),
                {"uid": str(url_id), "n": n, "sz": total_len},
            )
    except Exception as exc:
        logger.error("index_url_background: DB update failed for %s: %s", url_id, exc)


def _mark_failed(file_id: UUID, exc: Exception) -> None:
    try:
        with engine.begin() as conn:
            from sqlalchemy import text
            conn.execute(
                text("UPDATE files SET status='failed', error=:error WHERE id=:fid"),
                {"fid": str(file_id), "error": str(exc)[:2000]},
            )
    except Exception as db_err:
        logger.error("_mark_failed: DB update error for %s: %s", file_id, db_err)


def _mark_url_failed(url_id: UUID, exc: Exception) -> None:
    try:
        with engine.begin() as conn:
            from sqlalchemy import text
            conn.execute(
                text("UPDATE knowledge_urls SET status='failed', error=:error WHERE id=:uid"),
                {"uid": str(url_id), "error": str(exc)[:2000]},
            )
    except Exception as db_err:
        logger.error("_mark_url_failed: DB update error for %s: %s", url_id, db_err)
