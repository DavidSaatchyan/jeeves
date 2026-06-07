"""Chroma client singleton + embedding with batching, rate limiting, retry."""
from __future__ import annotations

import logging
import threading
import time
from urllib.parse import urlparse
from uuid import UUID

import chromadb
from openai import OpenAI

from ..config import get_settings
from .config import EMBED_MODEL, EMBEDDING_VERSION

logger = logging.getLogger(__name__)
_settings = get_settings()

_chroma_client = None
_chroma_lock = threading.Lock()

_CHUNK_SIZE = 100
_MAX_RETRIES = 3
_INITIAL_BACKOFF = 1.0

_RATE_LIMIT_RPM = 3000
_BUCKET_TOKENS = _RATE_LIMIT_RPM
_BUCKET_REFILL_RATE = _RATE_LIMIT_RPM / 60.0
_BUCKET_MAX = _RATE_LIMIT_RPM
_last_refill = time.monotonic()
_bucket_lock = threading.Lock()


def _acquire(count: int = 1) -> None:
    global _BUCKET_TOKENS, _last_refill
    with _bucket_lock:
        now = time.monotonic()
        elapsed = now - _last_refill
        _BUCKET_TOKENS = min(_BUCKET_MAX, _BUCKET_TOKENS + elapsed * _BUCKET_REFILL_RATE)
        _last_refill = now
        if _BUCKET_TOKENS >= count:
            _BUCKET_TOKENS -= count
            return
        sleep_needed = (count - _BUCKET_TOKENS) / _BUCKET_REFILL_RATE
        _BUCKET_TOKENS = 0
    time.sleep(sleep_needed)


def _openai() -> OpenAI:
    return OpenAI(api_key=_settings.openai_api_key)


def _chroma():
    global _chroma_client
    if _chroma_client is not None:
        return _chroma_client

    with _chroma_lock:
        if _chroma_client is not None:
            return _chroma_client

        if _settings.chroma_url:
            u = urlparse(_settings.chroma_url)
            _chroma_client = chromadb.HttpClient(host=u.hostname or "chroma", port=u.port or 8000)
        elif _settings.chroma_path:
            _chroma_client = chromadb.PersistentClient(path=_settings.chroma_path)
        else:
            raise RuntimeError("Neither CHROMA_URL nor CHROMA_PATH is configured")
        return _chroma_client


def _collection(tenant_id: UUID | str):
    name = f"tenant_{str(tenant_id).replace('-', '')}"
    return _chroma().get_or_create_collection(
        name=name,
        metadata={"hnsw:space": "cosine", "embedding_version": EMBEDDING_VERSION},
    )


def embed_batch(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    result: list[list[float]] = []
    for i in range(0, len(texts), _CHUNK_SIZE):
        chunk = texts[i:i + _CHUNK_SIZE]
        _acquire(len(chunk))
        for attempt in range(_MAX_RETRIES):
            try:
                resp = _openai().embeddings.create(model=EMBED_MODEL, input=chunk)
                result.extend([d.embedding for d in resp.data])
                break
            except Exception as e:
                if attempt < _MAX_RETRIES - 1:
                    backoff = _INITIAL_BACKOFF * (2 ** attempt)
                    logger.warning(
                        "embed_batch chunk %d/%d failed (attempt %d): %s, retry in %.1fs",
                        i // _CHUNK_SIZE + 1, (len(texts) + _CHUNK_SIZE - 1) // _CHUNK_SIZE,
                        attempt + 1, e, backoff,
                    )
                    time.sleep(backoff)
                else:
                    logger.error(
                        "embed_batch chunk %d/%d failed after %d retries: %s",
                        i // _CHUNK_SIZE + 1, (len(texts) + _CHUNK_SIZE - 1) // _CHUNK_SIZE,
                        _MAX_RETRIES, e,
                    )
                    raise
    return result
