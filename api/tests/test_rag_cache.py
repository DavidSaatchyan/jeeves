"""Unit tests for app.rag.cache: semantic cache, in-memory LRU, Redis."""
from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, patch


from app.rag.cache import (
    _InMemoryCache,
    _make_cache_key,
    cache_lookup,
    cache_store,
    invalidate_cache,
)


# ── _InMemoryCache ──────────────────────────────────────────────────────


class TestInMemoryCache:
    def test_set_and_get(self):
        cache = _InMemoryCache(maxsize=10)
        cache.set("k1", [{"text": "hello"}])
        result = cache.get("k1")
        assert result == [{"text": "hello"}]

    def test_get_missing_key(self):
        cache = _InMemoryCache(maxsize=10)
        assert cache.get("missing") is None

    def test_expired_entry(self):
        cache = _InMemoryCache(maxsize=10)
        cache.set("k1", [{"text": "hello"}], ttl=-1)
        time.sleep(0.01)
        assert cache.get("k1") is None

    def test_eviction_lru(self):
        cache = _InMemoryCache(maxsize=2)
        cache.set("a", [1])
        cache.set("b", [2])
        cache.set("c", [3])
        assert cache.get("a") is None
        assert cache.get("b") is not None
        assert cache.get("c") is not None

    def test_get_refreshes_lru_order(self):
        cache = _InMemoryCache(maxsize=2)
        cache.set("a", [1])
        cache.set("b", [2])
        cache.get("a")
        cache.set("c", [3])
        assert cache.get("a") is not None
        assert cache.get("b") is None

    def test_thread_safety(self):
        cache = _InMemoryCache(maxsize=100)
        import threading
        errors = []

        def worker():
            try:
                for i in range(100):
                    cache.set(f"k{i}", [i])
                    cache.get(f"k{i}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors


# ── _make_cache_key ─────────────────────────────────────────────────────


class TestMakeCacheKey:
    def test_returns_string(self):
        key = _make_cache_key("hello")
        assert isinstance(key, str)
        assert key.startswith("rag_cache:")

    def test_different_queries_different_keys(self):
        k1 = _make_cache_key("hello")
        k2 = _make_cache_key("world")
        assert k1 != k2

    def test_same_query_same_key(self):
        assert _make_cache_key("test") == _make_cache_key("test")


# ── cache_lookup / cache_store ──────────────────────────────────────────


class TestCacheLookup:
    def test_disabled_returns_none(self):
        with patch("app.rag.cache.SEMANTIC_CACHE", False):
            assert cache_lookup("test") is None

    @patch("app.rag.cache.embed_batch", return_value=[[0.1, 0.2]])
    def test_memory_miss_returns_none(self, mock_embed):
        with patch("app.rag.cache.SEMANTIC_CACHE", True):
            with patch("app.rag.cache._in_memory.get", return_value=None):
                assert cache_lookup("test") is None

    @patch("app.rag.cache.embed_batch", return_value=[[0.1, 0.2]])
    def test_memory_hit_returns_cached(self, mock_embed):
        with patch("app.rag.cache.SEMANTIC_CACHE", True):
            with patch("app.rag.cache._in_memory.get", return_value=[{"text": "cached"}]):
                result = cache_lookup("test")
                assert result == [{"text": "cached"}]

    @patch("app.rag.cache.embed_batch", side_effect=Exception("embed fail"))
    def test_embedding_failure_returns_none(self, mock_embed):
        with patch("app.rag.cache.SEMANTIC_CACHE", True):
            assert cache_lookup("test") is None

    @patch("app.rag.cache.embed_batch", return_value=[[0.1, 0.2]])
    def test_redis_hit_returns_cached(self, mock_embed):
        mock_redis = MagicMock()
        mock_redis.get.return_value = json.dumps({
            "embedding": [0.1, 0.2],
            "results": [{"text": "redis_cached"}],
        })

        with patch("app.rag.cache.SEMANTIC_CACHE", True):
            with patch("app.rag.cache._get_redis", return_value=mock_redis):
                with patch("app.rag.cache._in_memory.get", return_value=None):
                    with patch("app.rag.cache._cosine_sim", return_value=0.99):
                        result = cache_lookup("test")
                        assert result == [{"text": "redis_cached"}]

    @patch("app.rag.cache.embed_batch", return_value=[[0.1, 0.2]])
    def test_redis_low_similarity_falls_to_memory(self, mock_embed):
        mock_redis = MagicMock()
        mock_redis.get.return_value = json.dumps({
            "embedding": [0.5, 0.5],
            "results": [{"text": "different"}],
        })

        with patch("app.rag.cache.SEMANTIC_CACHE", True):
            with patch("app.rag.cache._get_redis", return_value=mock_redis):
                with patch("app.rag.cache._in_memory.get", return_value=None):
                    with patch("app.rag.cache._cosine_sim", return_value=0.5):
                        result = cache_lookup("test")
                        assert result is None


class TestCacheStore:
    @patch("app.rag.cache.embed_batch", return_value=[[0.1, 0.2]])
    def test_disabled_does_nothing(self, mock_embed):
        with patch("app.rag.cache.SEMANTIC_CACHE", False):
            cache_store("test", [{"text": "x"}])
            mock_embed.assert_not_called()

    @patch("app.rag.cache.embed_batch", return_value=[[0.1, 0.2]])
    def test_stores_in_memory(self, mock_embed):
        mock_memory = MagicMock()
        with patch("app.rag.cache.SEMANTIC_CACHE", True):
            with patch("app.rag.cache._in_memory", mock_memory):
                cache_store("test", [{"text": "x"}])
                mock_memory.set.assert_called_once()

    @patch("app.rag.cache.embed_batch", side_effect=Exception("fail"))
    def test_embedding_failure_does_not_store(self, mock_embed):
        with patch("app.rag.cache.SEMANTIC_CACHE", True):
            cache_store("test", [{"text": "x"}])

    @patch("app.rag.cache.embed_batch", return_value=[[0.1, 0.2]])
    def test_stores_in_redis(self, mock_embed):
        mock_redis = MagicMock()
        with patch("app.rag.cache.SEMANTIC_CACHE", True):
            with patch("app.rag.cache._get_redis", return_value=mock_redis):
                with patch("app.rag.cache._in_memory"):
                    cache_store("test", [{"text": "x"}])
                    mock_redis.setex.assert_called_once()


class TestInvalidateCache:
    def test_no_redis_skips(self):
        with patch("app.rag.cache._get_redis", return_value=None):
            invalidate_cache()

    def test_redis_clears_keys(self):
        mock_redis = MagicMock()
        mock_redis.scan_iter.return_value = ["rag_cache:a", "rag_cache:b"]
        with patch("app.rag.cache._get_redis", return_value=mock_redis):
            invalidate_cache()
        assert mock_redis.delete.call_count == 2

    def test_redis_exception_logs_warning(self):
        mock_redis = MagicMock()
        mock_redis.scan_iter.side_effect = Exception("Redis down")
        with patch("app.rag.cache._get_redis", return_value=mock_redis):
            invalidate_cache()
