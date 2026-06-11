---
name: rag-optimizer
description: "RAG pipeline optimization specialist for production systems. Analyzes existing RAG pipelines (chunking, embedding, retrieval, reranking, caching) and applies targeted optimizations: query expansion, HyDE, hybrid search, MMR tuning, reranker selection, semantic cache strategies, and evaluation-driven iteration. Includes 10 optimization patterns, 8 quality metrics, and 6 workflow templates."
license: MIT
metadata:
  author: OpenFlo
  version: "2.0.0"
  domain: rag
  triggers: rag, retrieval, embedding, chunking, rerank, hyde, query expansion, semantic cache, hybrid search
  role: optimizer
  scope: pipeline
  output-format: implementation plan + code changes
---

# RAG Optimizer — Pipeline Optimization Specialist

Analyzes production RAG pipelines and applies targeted optimizations. Covers chunking, embedding, retrieval, reranking, caching, and evaluation.

## Pipeline Architecture Reference

```
[Documents] → [Chunking] → [Embedding] → [Index] → [Query] → [Retrieval] → [Reranking] → [Generation]
                    │              │           │           │            │
               token-aware     OpenAI      ChromaDB   translation    Cohere/BGE
               heading split   ada-003               + expansion    CrossEncoder
               tiktoken                              + HyDE
```

## Jeeves RAG Pipeline (Analyzed)

### File Layout
| File | Lines | Role |
|------|-------|------|
| `api/app/rag/client.py` | 108 | ChromaDB singleton, OpenAI embedding, rate-limited token bucket (3000 RPM) |
| `api/app/rag/chunking.py` | 363 | Token-aware chunking (tiktoken cl100k_base), heading-split for MD/PDF, recursive para→sent→window, deterministic hashes |
| `api/app/rag/engine.py` | 208 | `search()`, `index_file()`, `index_text()`, `delete_file()`, `count_chunks_by_source()` |
| `api/app/rag/reranker.py` | 85 | Cohere Rerank 3.5 with BGE CrossEncoder fallback |
| `api/app/rag/mmr.py` | 76 | MMR diversification, cosine similarity |
| `api/app/rag/cache.py` | 149 | Semantic cache (Redis + in-memory LRU), exact MD5 key, cosine threshold 0.95 |
| `api/app/rag/config.py` | 22 | YAML-backed config: `top_k=15`, `distance_threshold=0.85`, `mmr_lambda=0.0` |
| `api/app/rag/translation.py` | 60 | Query translation for non-English, dual search + RRF merge (weights [1.0, 1.2]) |
| `api/app/rag/citation_guard.py` | 91 | Token-overlap citation validation (word-level, not semantic) |
| `api/app/rag/maintenance.py` | 68 | Dedup by filename+chunk_hash, orphan purge |
| `api/app/rag/batch.py` | 45 | Chroma batch operations (500 items) |
| `api/app/rag/products.py` | 99 | Product catalog indexing |
| `api/app/rag/crm_indexer.py` | 254 | HMS data indexing (services, practitioners, clinic) |
| `api/app/rag/background.py` | 89 | Async background indexing (files + URLs) |
| `api/app/knowledge/url_extractor.py` | 283 | URL fetching, trafilatura + bs4 extraction, structured (heading, body) |
| `api/app/knowledge/sync.py` | 421 | CRM sync orchestration (HMS + legacy Cliniko), SQL+Chroma |

### Current Quality Levers (config.yaml)
| Parameter | Current | Effect |
|-----------|---------|--------|
| `embedding_model` | text-embedding-3-small | 1536-dim, high quality |
| `top_k` | 15 | Initial retrieval count |
| `distance_threshold` | 0.85 | Cosine distance (lower=stricter) |
| `mmr_lambda` | 0.0 | **Disabled** — no diversity enforcement |
| `reranker.provider` | "" (disabled) | **No reranking by default** |
| `query_translation` | false | **Disabled** — no multilingual support |
| `semantic_cache` | false | **Disabled** — no caching |
| `citation_guard` | false | **Disabled** — no citation validation |
| `chat_threshold` | 0.8 | Stricter threshold for chat |

### Raw Search Flow (engine.py:133-208)
1. Embed query via `embed_batch([query])[0]`
2. Chroma `query()` with `n_results=top_k`, `include=["documents","metadatas","distances"]`
3. Dedup by `chunk_hash`
4. Threshold filter: `distance <= DISTANCE_THRESHOLD`
5. Sort by distance ascending
6. No query expansion, no HyDE, no hybrid (keyword+vector)

## 10 Optimization Patterns

### 1. Query Expansion (HyDE)
**Problem**: Single query embedding misses semantic variants. "What costs less than $50?" vs "cheap services" embed differently.

**Implementation** (`api/app/rag/expansion.py`):
```python
# Hypothetical Document Embeddings
HYDE_PROMPT = """Given a question, generate a hypothetical document that would answer it.
Question: {query}
Document:"""

def expand_query(query: str) -> list[str]:
    """Return list of query variants for multi-query retrieval."""
    variants = [query]
    # Generate 2 alternative phrasings via LLM
    alt = llm_complete(f"Rephrase this question 2 ways: {query}")
    variants.extend(alt.strip().split("\n"))
    return variants

def hyde_search(query: str) -> list[dict]:
    """Generate hypothetical doc, embed that instead of raw query."""
    hypo_doc = llm_complete(HYDE_PROMPT.format(query=query))
    return search(..., query=hypo_doc)  # embed hypo doc, not query
```

**Integration point**: `engine.py:search()` — add optional `query_expansion="hyde"` param.

### 2. MMR Diversity (Enabled)
**Problem**: `mmr_lambda=0.0` means no diversity — top-N results may all come from one document.

**Fix** (`config.py` and `engine.py`):
```python
# config.py
MMR_LAMBDA = float(_rag_cfg.get("mmr_lambda", 0.3))  # Default 0.3

# engine.py — after threshold filter
if MMR_LAMBDA > 0.0 and len(out) > 1:
    out = mmr_diversify(out, query, lambda_=MMR_LAMBDA, top_k=top_k)
```

**Tuning**: 0.3 = balanced relevance+diversity, 0.5 = equal weight, 0.7 = diversity-heavy.

### 3. Hybrid Search (Vector + Keyword)
**Problem**: Purely semantic search misses exact keyword matches (e.g., "23-25G needle", exact codes).

**Implementation** (`api/app/rag/hybrid.py`):
```python
import re
from collections import Counter

BM25_K1 = 1.5
BM25_B = 0.75

def _tokenize(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())

def bm25_scores(query: str, docs: list[str]) -> list[float]:
    """BM25Okapi scoring against pre-computed doc corpus."""
    q_tokens = _tokenize(query)
    n_docs = len(docs)
    avgdl = sum(len(_tokenize(d)) for d in docs) / max(n_docs, 1)
    dfs: Counter = Counter()
    for d in docs:
        for t in set(_tokenize(d)):
            dfs[t] += 1
    scores = []
    for d in docs:
        d_tokens = _tokenize(d)
        dl = len(d_tokens)
        score = 0.0
        for t in q_tokens:
            if t not in dfs:
                continue
            tf = d_tokens.count(t)
            idf = math.log((n_docs - dfs[t] + 0.5) / (dfs[t] + 0.5) + 1)
            num = tf * (BM25_K1 + 1)
            den = tf + BM25_K1 * (1 - BM25_B + BM25_B * dl / avgdl)
            score += idf * num / den
        scores.append(score)
    return scores
```

**Integration**: `engine.py:search()` — run BM25 over top-k semantic results, RRF merge with `k=60`.

### 4. Semantic Cache (Enabled + Fuzzy Key)
**Problem**: Exact MD5 key means "price of MRI" ≠ "MRI cost" — no cache hit for similar queries.

**Fix** (`cache.py`):
```python
# Replace exact MD5 key with embedding-based lookup
def cache_lookup(query: str) -> list[dict] | None:
    if not SEMANTIC_CACHE:
        return None
    q_emb = embed_batch([query])[0]
    # Scan recent cache entries by cosine similarity
    for cached_query, (cached_emb, results) in _in_memory_cache.items():
        if cosine_sim(q_emb, cached_emb) >= _COSINE_THRESHOLD:
            return results
    # Redis: store embeddings, query by vector similarity if available
    ...
```

Add TTL-based cache eviction and LRU within Redis.

### 5. Chunking Optimization
**Problem (PDF)**: ALL-CAPS heading heuristics miss non-ALL-CAPS headings.

**Fix** (`chunking.py`): Add pypdf heading extraction via font size analysis:
```python
def _extract_pdf_units_smart(path: Path) -> list[_Unit]:
    """Use font size changes to detect headings (no ALL-CAPS assumption)."""
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    units = []
    cur_section = ""
    buf = []
    for page in reader.pages:
        for block in page.get_text("dict")["blocks"]:
            if block["type"] != 0:  # non-text
                continue
            for line in block["lines"]:
                text = "".join(s["text"] for s in line["spans"])
                font_size = max(s["size"] for s in line["spans"]) if line["spans"] else 12
                # Font size > 1.3x body text → heading
                if _is_likely_heading_font(text.strip(), font_size, base_size=12):
                    if buf:
                        units.append(_Unit(text="\n".join(buf), section=cur_section))
                        buf = []
                    cur_section = text.strip()
                else:
                    buf.append(text)
    if buf:
        units.append(_Unit(text="\n".join(buf), section=cur_section))
    return units or [_Unit(text="")]
```

### 6. Reranker Enablement
**Problem**: No reranking = raw cosine distance only, ignores semantic relevance nuances.

**Fix** (`config.yaml`):
```yaml
rag:
  reranker:
    provider: "bge"  # or "cohere"
    model: "BAAI/bge-reranker-v2-m3"  # free, 4.8GB VRAM
    # Cohere: model: "rerank-v3.5", requires API key
```

**When to use which**:
| Provider | Cost | Quality | When |
|----------|------|---------|------|
| None (default) | Free | Baseline | Dev, low traffic |
| BGE (local) | Free (RAM) | Good | Self-hosted, <100 QPS |
| Cohere | ~$0.001/doc | Excellent | Production, high accuracy needs |

### 7. Query Translation Enhancement
**Problem**: Current ASCII heuristic (`_is_mostly_ascii`) is naive — it detects only >90% ASCII.

**Fix** (`translation.py`):
```python
LANG_DETECT_THRESHOLD = 0.3  # lower = more sensitive to non-English

async def translate_and_search(...):
    lang = await detect_language(query)  # use lingua-py or fasttext
    if lang == "en":
        return await asyncio.to_thread(rag_search, ...)
    translated = await translate_query(query)
    en_results = await asyncio.to_thread(rag_search, ..., query=translated)
    if lang in ("ru", "zh", "ar"):
        # Low-resource: also weigh original-language search
        orig_results = await asyncio.to_thread(rag_search, ..., query=query)
        return _rrf_merge(en_results, orig_results, weights=[1.5, 1.0])
    return en_results
```

### 8. Citation Guard Semantic Upgrade
**Problem**: Word-level token overlap misses semantically equivalent citations.

**Fix** (`citation_guard.py`):
```python
def _citation_found_semantic(citation_text: str, chunks: list[dict]) -> bool:
    """Use embedding cosine similarity instead of token overlap."""
    c_emb = embed_batch([citation_text])[0]  # single embedding
    for chunk in chunks:
        if not chunk.get("text"):
            continue
        # If chunk already has stored embedding, use it; else compute
        chunk_emb = _get_chunk_embedding(chunk)
        if cosine_sim(c_emb, chunk_emb) >= 0.85:
            return True
    return False
```

### 9. Performance: Embedding Cache
**Problem**: `embed_batch` called once per search + once per cache lookup + once per MMR = 3x embedding API calls per query.

**Fix**: Cache the query embedding for the life of the request:
```python
# engine.py search() — thread-local cache
_query_embedding_cache: dict[str, list[float]] = {}

def _get_query_embedding(query: str) -> list[float]:
    if query not in _query_embedding_cache:
        _query_embedding_cache[query] = embed_batch([query])[0]
    return _query_embedding_cache[query]
```

### 10. Evaluation-Driven Tuning
**Problem**: No systematic evaluation — quality changes are subjective.

**Implementation** (`scripts/eval_rag.py`):
```python
"""Evaluate RAG pipeline against KB_TEST_PLAN.md scenarios."""
import json
from pathlib import Path

METRICS = {
    "faithfulness": "answer does not contradict context",
    "answer_relevancy": "answer addresses the query",
    "context_precision": "top-k includes relevant chunks",
    "context_recall": "all relevant chunks retrieved",
    "hallucination_rate": "percentage of 'I don't know' when info absent",
}

def evaluate(kb_test_plan: Path, search_fn, top_k=10, threshold=0.85):
    scenarios = parse_test_plan(kb_test_plan)
    results = {"pass": 0, "fail": 0, "by_category": {}}
    for s in scenarios:
        chunks = search_fn(s["query"], top_k=top_k, threshold=threshold)
        # Check: does top chunk contain the expected answer?
        found = any(s["expected"].lower() in c["text"].lower() for c in chunks)
        results["pass" if found else "fail"] += 1
        cat = s.get("category", "uncategorized")
        results["by_category"].setdefault(cat, {"pass": 0, "fail": 0})
        results["by_category"][cat]["pass" if found else "fail"] += 1
    return results
```

## Quality Metrics

| Metric | Target | How to Measure |
|--------|--------|----------------|
| Top-1 hit rate | >80% | Does the #1 chunk contain the answer? |
| Top-5 recall | >90% | Is the answer in the top 5 chunks? |
| Precision@K | >60% | How many of top-K are relevant? |
| Hallucination rate | <5% | For "no info" queries, answer says "I don't know" |
| Latency P95 | <500ms | End-to-end search time (excl. LLM generation) |
| Dedup effectiveness | <2% | Duplicate chunk_hash in results |
| Cache hit rate | >30% | (with semantic cache enabled) |
| Translation accuracy | >85% | For non-English queries, correct retrieval |

## Workflow Patterns

### Pattern 1: Quick Wins (30 min)
1. Enable MMR: set `mmr_lambda=0.3` in config
2. Enable reranker: set `reranker.provider="bge"`
3. Measure improvement with `eval_rag.py`

### Pattern 2: Full Optimization (2-4 hours)
1. Run `eval_rag.py` → baseline metrics
2. Enable MMR + reranker → measure delta
3. Implement query expansion (HyDE) → measure delta
4. Enable semantic cache → measure latency delta
5. Implement hybrid search → measure recall delta
6. Run full eval → report improvements

### Pattern 3: Precision Tuning
**When**: Hallucination rate >5%, answers too broad
- Lower `distance_threshold` to 0.75
- Enable `citation_guard`
- Increase `MMR_LAMBDA` to 0.5 for more diverse sources
- Set `top_k` to 8 (narrower initial pool)

### Pattern 4: Recall Tuning
**When**: Missing relevant chunks, "I don't know" when info exists
- Increase `top_k` to 25
- Lower `distance_threshold` to 0.9
- Enable `query_translation`
- Enable HyDE expansion
- Add BM25 hybrid search

## Review Checklist

- [ ] MMR enabled (lambda 0.2-0.5)?
- [ ] Reranker configured (BGE or Cohere)?
- [ ] Threshold not too aggressive (<0.8 cuts too much)?
- [ ] Chunk size appropriate for domain (512 tokens for medical)?
- [ ] Semantic cache enabled with fuzzy matching?
- [ ] Query embedding cached per-request?
- [ ] `chunk_hash` dedup working?
- [ ] No orphan chunks accumulating?
- [ ] Batch sizing optimal (500 items)?
- [ ] Rate limiting appropriate for API tier?
- [ ] Query translation config aligned with user language mix?
- [ ] KB_TEST_PLAN scenarios pass >80%?

## Key Files (Jeeves Project)

| Path | Purpose |
|------|---------|
| `api/app/rag/engine.py:133-208` | `search()` — core retrieval |
| `api/app/rag/chunking.py:269-345` | `build_chunks()` — chunking pipeline |
| `api/app/rag/config.py:1-22` | All RAG config parameters |
| `api/app/rag/reranker.py:12-85` | Reranking wrapper |
| `api/app/rag/mmr.py:10-76` | MMR diversification |
| `api/app/rag/cache.py:88-149` | Semantic cache logic |
| `api/app/rag/translation.py:15-60` | Query translation pipeline |
| `api/app/rag/citation_guard.py:34-91` | Citation validation |
| `api/app/rag/client.py:80-108` | Embedding with retry + rate limit |
| `requirements/KB_TEST_PLAN.md` | 500+ line test plan, 80+ real queries |
| `api/app/knowledge/url_extractor.py` | URL ingestion pipeline |
| `api/app/knowledge/sync.py` | CRM sync pipeline |
