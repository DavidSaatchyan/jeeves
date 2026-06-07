"""Chroma batch helpers — col.add/delete by 500 items."""
from __future__ import annotations

import logging
from typing import Any

_BATCH_SIZE = 500

logger = logging.getLogger(__name__)


def batch_add(
    col: Any,
    ids: list[str],
    embeddings: list[list[float]] | None = None,
    documents: list[str] | None = None,
    metadatas: list[dict] | None = None,
) -> None:
    total = len(ids)
    for i in range(0, total, _BATCH_SIZE):
        end = min(i + _BATCH_SIZE, total)
        kwargs: dict[str, Any] = {"ids": ids[i:end]}
        if embeddings is not None:
            kwargs["embeddings"] = embeddings[i:end]
        if documents is not None:
            kwargs["documents"] = documents[i:end]
        if metadatas is not None:
            kwargs["metadatas"] = metadatas[i:end]
        try:
            col.add(**kwargs)
        except Exception as e:
            logger.error("batch_add chunk %d/%d failed: %s", i // _BATCH_SIZE + 1,
                         (total + _BATCH_SIZE - 1) // _BATCH_SIZE, e)
            raise


def batch_delete_ids(col: Any, ids: list[str]) -> None:
    for i in range(0, len(ids), _BATCH_SIZE):
        chunk = ids[i:i + _BATCH_SIZE]
        try:
            col.delete(ids=chunk)
        except Exception as e:
            logger.error("batch_delete_ids chunk %d/%d failed: %s",
                         i // _BATCH_SIZE + 1, (len(ids) + _BATCH_SIZE - 1) // _BATCH_SIZE, e)
            raise
