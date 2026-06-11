"""RAG: chunking, embedding, Chroma storage, similarity search."""
from __future__ import annotations

from .cache import cache_lookup, cache_store, invalidate_cache
from .citation_guard import validate as validate_citations
from .config import (
    CHAT_THRESHOLD,
    CITATION_GUARD,
    DISTANCE_THRESHOLD,
    EMBED_MODEL,
    EMBEDDING_VERSION,
    MMR_LAMBDA,
    QUERY_TRANSLATION,
    RERANKER_PROVIDER,
    SEMANTIC_CACHE,
    TOP_K,
)
from .engine import count_chunks_by_source, delete_file, get_chunks_for_file, index_file, index_structured_text, index_text, search
from .grounding import validate_grounding
from .maintenance import deduplicate_collection, purge_orphans
from .mmr import mmr_diversify
from .products import delete_products_by_batch, index_products
from .reranker import rerank as rerank_docs
from .translation import translate_and_search

__all__ = [
    "CACHE_TTL_SECONDS",
    "CHAT_THRESHOLD",
    "CITATION_GUARD",
    "DISTANCE_THRESHOLD",
    "EMBED_MODEL",
    "EMBEDDING_VERSION",
    "MMR_LAMBDA",
    "QUERY_TRANSLATION",
    "RERANKER_PROVIDER",
    "SEMANTIC_CACHE",
    "TOP_K",
    "cache_lookup",
    "cache_store",
    "count_chunks_by_source",
    "delete_file",
    "delete_products_by_batch",
    "deduplicate_collection",
    "get_chunks_for_file",
    "index_file",
    "index_products",
    "index_structured_text",
    "index_text",
    "invalidate_cache",
    "mmr_diversify",
    "purge_orphans",
    "rerank_docs",
    "search",
    "translate_and_search",
    "validate_citations",
    "validate_grounding",
]
