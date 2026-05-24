from __future__ import annotations

from ..config import get_settings, get_yaml_config

_settings = get_settings()
_rag_cfg = get_yaml_config().get("rag", {})
EMBED_MODEL = _rag_cfg.get("embedding_model", "text-embedding-3-small")
TOP_K = int(_rag_cfg.get("top_k", 15))
DISTANCE_THRESHOLD = float(_rag_cfg.get("distance_threshold", 0.85))
EMBEDDING_VERSION = f"{EMBED_MODEL}:v1"
