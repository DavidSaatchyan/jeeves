"""RAG: chunking, embedding, Chroma storage, similarity search."""
from __future__ import annotations

from .config import DISTANCE_THRESHOLD, EMBED_MODEL, EMBEDDING_VERSION, TOP_K
from .engine import _count_all_chunks, delete_file, index_file, search
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
    "index_file",
    "index_products",
    "purge_orphans",
    "search",
]
