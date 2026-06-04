"""RAG: chunking, embedding, Chroma storage, similarity search."""
from __future__ import annotations

from .config import DISTANCE_THRESHOLD, EMBED_MODEL, EMBEDDING_VERSION, TOP_K
from .engine import delete_file, get_chunks_for_file, index_file, index_structured_text, index_text, search
from .maintenance import deduplicate_collection, purge_orphans
from .products import delete_products_by_batch, index_products

__all__ = [
    "DISTANCE_THRESHOLD",
    "EMBED_MODEL",
    "EMBEDDING_VERSION",
    "TOP_K",
    "delete_file",
    "delete_products_by_batch",
    "deduplicate_collection",
    "get_chunks_for_file",
    "index_file",
    "index_products",
    "index_structured_text",
    "index_text",
    "purge_orphans",
    "search",
]
