from __future__ import annotations

from ..config import get_settings, get_yaml_config

_settings = get_settings()
_rag_cfg = get_yaml_config().get("rag", {})

EMBED_MODEL = _rag_cfg.get("embedding_model", "text-embedding-3-small")
TOP_K = int(_rag_cfg.get("top_k", 15))
DISTANCE_THRESHOLD = float(_rag_cfg.get("distance_threshold", 0.85))
CHAT_THRESHOLD = float(_rag_cfg.get("chat_threshold", 0.8))
EMBEDDING_VERSION = f"{EMBED_MODEL}:v1"

QUERY_TRANSLATION = bool(_rag_cfg.get("query_translation", False))
MMR_LAMBDA = float(_rag_cfg.get("mmr_lambda", 0.0))
SEMANTIC_CACHE = bool(_rag_cfg.get("semantic_cache", False))
CITATION_GUARD = bool(_rag_cfg.get("citation_guard", False))

RERANKER_CFG = _rag_cfg.get("reranker", {}) or {}
RERANKER_PROVIDER = (RERANKER_CFG.get("provider") or "").strip()
RERANKER_API_KEY = (RERANKER_CFG.get("api_key") or "").strip()
RERANKER_MODEL = RERANKER_CFG.get("model", "rerank-v3.5")
