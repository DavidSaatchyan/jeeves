from __future__ import annotations

import logging
import threading
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
    resp = _openai().embeddings.create(model=EMBED_MODEL, input=texts)
    return [d.embedding for d in resp.data]
