# RAG Pipeline — Optimization & Fix Plan

> Based on Section 5 Hallucination & Robustness Audit (71 test cases) + pipeline architecture analysis.
> Current pass rate: ~75% (53/71). Target: 95%+.

---

## Summary of Current State

### Architecture Flow

```
User message → classify(kb_query) → cache_lookup() [DISABLED]
  → translate_and_search() [dual search EN + original]
    → engine.search() [OpenAI embed → Chroma cosine search, top_k=10]
  → _rrf_merge(kb_results, hms_results)
  → rerank_docs() [BGE cross-encoder]
  → mmr_diversify() [lambda=0.3] OR _diversify_results() [max 3/source → 5 total]
  → cache_store() [DISABLED]
  → build context blocks → call_structured(gpt-4o-mini, KBResponse, temp=0.0)
  → validate_citations() [token overlap guard]
  → _verify_against_context() [regex entity check]
  → deterministic_naturalize()
```

### Current Config (from `config.yaml`)

| Param | Value | Impact |
|-------|-------|--------|
| `top_k` | 15 (but code uses hardcoded 10) | Misses relevant chunks for aggregation |
| `distance_threshold` | 0.85 | OK |
| `chat_threshold` | 0.75 | Too strict — cuts entity matches at 61% |
| `mmr_lambda` | 0.3 | Reduces recall for enumeration queries |
| `semantic_cache` | `false` | Every query re-embeds + re-searches |
| `query_translation` | `true` | RRF merge EN+RU — active |
| `citation_guard` | `true` | Token overlap — active |
| `reranker` | BGE cross-encoder | Active, lightweight model |
| `llm` | gpt-4o-mini (structured) | Good but poor at grounding |

---

## Test Results Summary (Section 5)

| Category | Total | ✅ Pass | ❌ Fail | ⚠️ Partial | Critical (🔴) |
|----------|-------|---------|---------|-------------|---------------|
| 5.1 Faithfulness | 9 | 5 | 1 | 3 | 2 |
| 5.2 Extrinsic Hallucination | 9 | 9 | 0 | 0 | 0 |
| 5.3 Negative Rejection | 9 | 8 | 1 | 0 | 1 |
| 5.4 Knowledge Leakage | 8 | 7 | 1 | 0 | 0 |
| 5.5 Counterfactual Robustness | 4 | 4 | 0 | 0 | 0 |
| 5.6 Entity Accuracy | 5 | 1 | 3 | 1 | 2 |
| 5.7 Negation & Boundary | 6 | 0 | 2 | 4 | 1 |
| 5.8 Aggregation & Multi-Hop | 5 | 1 | 3 | 1 | 2 |
| 5.9 Source & Citation | 6 | 2 | 3 | 1 | 0 |
| 5.10 Noise Robustness | 6 | 5 | 1 | 0 | 0 |
| 5.11 Overconfidence | 5 | 4 | 1 | 0 | 0 |
| 5.12 Robustness | 3 | 0 | 2 | 1 | 0 |
| **Total** | **71** | **~53 (75%)** | **~14 (20%)** | **~4 (5%)** | **8** |

---

## Problem Catalog

### 1. Knowledge Leakage (LLM использует training data вместо контекста)

**Affected tests**: 5.1.4, 5.3.2, 5.4.8, 5.9.4

**Evidence**:
- `What is your street address?` → Petronas Towers + Kuala Lumpur climate/cuisine description
- `Where is My Clinic located?` → 3-paragraph guidebook text about KL
- `Is ECG the same as EKG?` → "Yes" from medical knowledge (KB only has "ECG: 12-lead")

**Root Cause**:
- `gpt-4o-mini` ignores system prompt "Never use your training knowledge" when context contains partial matches
- No programmatic grounding enforcement — `_verify_against_context()` is regex-only and skips common phrases
- Citation guard checks token overlap, not semantic grounding

**Fix**: P1.1 — Hallucination guard / P2.1 — Prompt improvement

---

### 2. Entity Resolution Fragility

**Affected tests**: 5.1.6, 5.6.3, 5.6.4, 5.8.3, 5.9.3

**Evidence**:
- `Is Mark Bolmer a Physician Assistant?` → 61% match, source found, but answer: "I don't know"
- `Tell me about Mark Bolmer` → "I don't know" (when asked with full name)
- Same query with just "Mark" → partially works
- `Is Lisa Lu a Medical Doctor?` → "Yes, you are correct" (passes but weak)
- `What is Lisa Lu's specialty?` → confused meta-response about "analysis text"

**Root Cause**:
- HMS data chunking stores practitioner fields as **individual chunks**:
  - Chunk 1: `§ Name → Mark`
  - Chunk 2: `§ Title → Mr`
  - Chunk 3: `§ Specialty → Physician Assistant`
- Full name "Mark Bolmer" matches only the "Mark" chunk at 32-61%
- `chat_threshold: 0.75` filters out low-score but still relevant chunks
- LLM receives only partial context (just "Mark") without "Physician Assistant"

**Fix**: P0.2 — HMS chunking / P1.3 — Threshold fix

---

### 3. Aggregation Failure (Incomplete Enumeration)

**Affected tests**: 5.7.3, 5.7.4, 5.8.1, 5.8.2, 5.8.4

**Evidence**:
- `What vaccines are available and how much?` → Only Flu ($35) + COVID (Free), misses Vaccination Standard ($40)
- `Which services cost between $100 and $200?` → Only Pediatric Checkup ($180), misses 7 others
- `How much does a consultation cost?` → Only Standard ($50), misses Initial ($100) + General ($150)
- `What imaging services and costs?` → Correct ✅ (passes, 6/6)

**Root Cause**:
- `_diversify_results()` caps at **max 3 chunks per source**, **5 total**
- `top_k` is **hardcoded 10** in `_handle_kb_query()` instead of `TOP_K = 15`
- `mmr_lambda: 0.3` further reduces diversity, picking 1 price per semantic group
- LLM receives incomplete set of prices/services — can't enumerate what it can't see

**Fix**: P0.3 — Aggregation detection + higher top_k for "list" queries

---

### 4. Negation Insensitivity

**Affected tests**: 5.7.1, 5.7.2

**Evidence**:
- `What procedures DON'T use a needle?` → "A blood draw is a standard venipuncture..." (blood draw IS a needle procedure)
- `Which injection routes are NOT intramuscular?` → Only oral, misses SC and IV

**Root Cause**:
- Embedding search retrieves by **semantic similarity** — "DON'T use a needle" embeds close to "needle procedures"
- Chroma has no `$not` operator in `where` clause
- BM25 hybrid search not implemented (Chroma doesn't support it natively)
- No query rewriting for negation

**Fix**: P1.2 — Query rewriting for negation

---

### 5. Conservative Rejection (False Negative)

**Affected tests**: 5.6.5, 5.10.4

**Evidence**:
- `What services does My Clinic offer?` → "I don't know" despite 4 relevant sources returned (hms-service, clinic, service_prices)
- `Can I get a blood test without insurance?` → "I don't know" despite context: "Insurance information is verified before the appointment begins"

**Root Cause**:
- Citation guard or `_verify_against_context()` may be over-aggressive
- LLM receives ambiguous context (multiple different sources) and falls back to "I don't know"
- KBResponse structured output may fail silently — `call_structured()` returns `None` and falls to `simple_llm_response` without proper error tracking

**Fix**: P2.x — Better fallback logging and structured output handling

---

### 6. Non-Determinism

**Affected tests**: 5.12.2, 5.12.3

**Evidence**:
- Same question "What services do you offer?" → first call: "I don't know", second call: correct, third call: "I don't know" again
- "Cost of MRI" → first: $1,200, second: from catalog CSV (stale), third: $1,200

**Root Cause**:
- MMR diversity (`lambda=0.3`) may shuffle results ordering
- Chroma query may return different ordering for concurrent writes
- Stale data from deleted catalog CSV pollutes results in some calls but not others
- No conversation-level caching or dedup

**Fix**: P0.1 — Semantic cache / P1.4 — Orphan cleanup + investigation

---

### 7. Stale / Orphan Chunks

**Affected tests**: 5.12.3

**Evidence**:
- "MRI price" query returns chunk from `catalog-import_20260523_093243.csv` — a deleted product import
- "Wireless Ergonomic Mouse" product showing in medical clinic RAG

**Root Cause**:
- File deletion → Chroma `delete(where={"file_id": ...})` may not execute properly
- `purge_orphans()` is not called automatically on delete
- Products index doesn't enforce type-based cleanup on reimport

**Fix**: P1.4 — Verify cleanup + add scheduled maintenance

---

### 8. HMS Chunking Deficiency

**Affected tests**: All entity resolution + 5.6.x, 5.9.x

**Evidence**:
- HMS practitioner chunks are **field-level** — name, title, specialty each separate
- One practitioner → 3+ Chroma chunks instead of 1 document
- No coherence between field for retrieval or LLM context

**Current chunk structure** (for Mark Bolmer):
```
§ Name    → Mark          (source: hms-practitioner-<id>)
§ Title   → Mr
§ Specialty → Physician Assistant...
```

**Desired structure**:
```
§ Practitioner Profile
Name: Mark Bolmer
Title: Mr
Specialty: Physician Assistant
Description: A highly trained, nationally certified...
```

**Fix**: P0.2 — Coalesce HMS practitioner/patient data into unitary chunks

---

## Optimization Plan

### P0 — Critical (fix now)

---

#### P0.1: Enable Semantic Cache + Increase `top_k`

**Files**: `api/app/rag/config.py`, `api/app/agents/incoming_line.py`

**Changes**:
1. `config.yaml`: `semantic_cache: true`
2. `incoming_line.py` line 110: change `10` → `TOP_K` (config value 15)
3. Verify Redis is available for distributed cache, fallback to in-memory LRU

**Expected impact**:
- Repeated queries 20-50x faster (no embedding, no Chroma search, no LLM)
- Higher recall for "list all" queries from 10→15 chunks

**Risk**: Low — cache is mature, in-memory fallback exists. TTL 24h.
**Time**: ~1h

---

#### P0.2: Fix HMS Chunking — Coalesce Practitioner/Cinic Documents

**Files**: `api/app/integrations/crm/*.py` (HMS sync), `api/app/rag/engine.py`

**Changes**:
1. Modify HMS practitioner sync to build **unitary profile documents** instead of field-level chunks
2. Each practitioner → 1-2 chunks with all fields merged:
   ```
   § Practitioner: Mark Bolmer
   Name: Mark
   Title: Mr  
   Specialty: Physician Assistant
   Description: A highly trained...
   ```
3. Apply same to clinic data — one chunk per clinic with full address
4. Re-index all existing HMS data (add version or migration)

**Expected impact**:
- Full name "Mark Bolmer" matches against unified text → higher cosine score
- LLM receives complete practitioner context (name + title + specialty together)
- 80%+ reduction in entity resolution failures

**Risk**: Medium — requires re-indexing. Backward compatible (old chunks get overwritten).
**Time**: ~4h

---

#### P0.3: Aggregation Detection — Higher `top_k` for "List All" Queries

**Files**: `api/app/agents/incoming_line.py`, possibly `api/app/core/ai/classify.py`

**Changes**:
1. Add `aggregation` intent to classifier (or detect via keywords: "list", "all", "what...do you offer", "what...available", "services", "prices", "costs")
2. For aggregation queries:
   - Bypass MMR diversity (`lambda=0.0`)
   - Use `_diversify_results()` with `max_per_group=5` instead of 3
   - Increase `top_k` to 30
   - No distance threshold relaxation (keep 0.75 chat_threshold for now)
3. For entity queries (single entity): keep current pipeline
4. For other queries: keep current pipeline

**Expected impact**:
- "What services cost between $100 and $200?" → all 8 services found instead of 1
- "What vaccines are available?" → all 3 vaccines found
- "How much does a consultation cost?" → $100 + $50 + $150

**Risk**: Low — heuristic-based, no architectural change.
**Time**: ~3h

---

### P1 — High (fix this sprint)

---

#### P1.1: Hallucination Guard — Post-hoc Entity Grounding

**Files**: `api/app/agents/incoming_line.py`, `api/app/rag/citation_guard.py`

**Changes**:
1. After `call_structured()` returns `KBResponse`, run entity grounding:
   - Extract all named entities from answer (names, locations, prices, procedures)
   - Cross-check each entity against context chunks
   - If any entity not found in context → reject answer
2. Extend `_verify_against_context()` to check:
   - Named entities (CapitalizedName words → must exist in context)
   - Numbers (prices, durations → must be within 1% of context values)
   - Locations (city names → must exist in context)
3. For knowledge leakage cases (Kuala Lumpur description):
   - Add "context boundary" check: if answer contains elaborative text not in any chunk, reject the elaborative part
4. Fallback: "I don't have that information in my knowledge base."

**Expected impact**:
- Eliminates Petronas Towers, ECG=EKG, KL climate descriptions
- Catches ~6 of the 8 critical hallucination failures

**Risk**: Low — soft block (rejects bad answers), doesn't affect correct answers.
**Time**: ~3h

---

#### P1.2: Query Rewriting for Negation

**Files**: `api/app/core/ai/generator.py` (new `rewrite_query` function), `api/app/rag/translation.py`

**Changes**:
1. Add `rewrite_query(user_query: str) → (rewritten: str, negated_terms: list[str])`:
   - Detect negation markers: NOT, DON'T, WITHOUT, EXCEPT, exclude
   - Extract the negated term (e.g., "needle" from "DON'T use a needle")
   - Return rewritten query without negation + list of negated terms
2. In search: search with rewritten query, then filter results to exclude negated terms
3. Works alongside translation (negation detection is cross-lingual)

**Expected impact**:
- "Procedures that DON'T use a needle" → searches for "medical procedures" then excludes needle-related chunks
- "Injection routes NOT intramuscular" → lists all routes excludes IM

**Risk**: Medium — simple heuristic for first version, can be improved with LLM-based rewriting later.
**Time**: ~3h

---

#### P1.3: Adjust `chat_threshold`

**Files**: `api/app/rag/config.py`, `api/app/config.yaml`

**Changes**:
1. `config.yaml`: `chat_threshold: 0.85` (match to `distance_threshold`)
2. Or introduce separate `entity_threshold: 0.90` for entity matching

**Background**:
- Current `chat_threshold = 0.75` means only chunks with distance < 0.75 (score > 0.25) are returned
- Mark Bolmer at 61% match = score 0.39 = distance 0.61 → passes 0.75, but barely
- With HMS chunking fix (P0.2), unified practitioner should score 70%+ naturally
- Threshold 0.85 gives more room for low-score but relevant chunks

**Expected impact**:
- More relevant context chunks reach the LLM
- Reduces false rejections (but may increase token usage)

**Risk**: Low — simple config change. Can be tuned down if noise increases.
**Time**: ~0.5h

---

#### P1.4: Fix Orphan Cleanup & Stale Data

**Files**: `api/app/rag/maintenance.py`, `api/app/knowledge/__init__.py`

**Changes**:
1. After every file/URL delete, call `purge_orphans()` for the tenant
2. Add scheduled periodic cleanup (e.g., every 6h via background task)
3. Add debug endpoint to list all chunks by source type for a tenant
4. Fix `purge_orphans` to also clean product catalog imports

**Expected impact**:
- No more stale CSV/product data in search results
- Chroma collection stays in sync with DB state
- Eliminates "Wireless Ergonomic Mouse" in medical RAG

**Risk**: Low — maintenance operation, no user-facing changes.
**Time**: ~2h

---

### P2 — Medium (next sprint)

---

#### P2.1: Improve LLM Prompt for Grounding

**Files**: `api/app/agents/incoming_line.py` (system/user prompt)

**Changes**:
1. Rewrite system prompt with stronger language:
   ```
   "You are a medical clinic assistant. Answer ONLY from the provided context.
   If the context only states a city/state, say only the city/state.
   NEVER add descriptions, landmarks, climate, or general knowledge about locations.
   Every fact in your answer must be directly supported by at least one [Document N] reference.
   If you cannot find a fact in the context, set missing_info=true."
   ```
2. Add 3 few-shot examples:
   - Correct: "Kuala Lumpur, WP Kuala Lumpur" (from context)
   - Wrong: "Kuala Lumpur is the capital city..." (hallucination)
   - Correct rejection: "I don't have this information"
3. Use paragraph-level citation (each paragraph references its source)

**Expected impact**:
- Reduces knowledge leakage by ~50% (remaining needs programmatic guard)
- More precise answers, less elaborative text
- Better citation accuracy

**Risk**: Low — prompt change, no code change. May increase token usage.
**Time**: ~1.5h

---

#### P2.2: Structured Output Error Handling

**Files**: `api/app/agents/incoming_line.py`

**Changes**:
1. When `call_structured()` returns `None`, log the full prompt + response for debugging
2. Add detailed error metrics (count of None returns per tenant)
3. Fix the meta-response issue ("I cannot provide a final answer without detailed analysis"):
   - This is the LLM being confused by the structured output schema
   - Add stricter prompt formatting for the JSON schema

**Expected impact**:
- Fewer confused responses (5.11.3)
- Better visibility into structured output failures

**Risk**: Low
**Time**: ~1h

---

#### P2.3: MMR Tuning for Aggregation Queries

**Files**: `api/app/rag/mmr.py`, config

**Changes**:
1. For aggregation queries (detected in P0.3): skip MMR entirely (`lambda=0.0`)
2. For entity queries: keep `lambda=0.3`
3. For general queries: tune `lambda` based on query type

**Expected impact**:
- Aggregation: complete enumeration, no diversity loss
- Entity: still gets diverse but focused results
- General: balanced

**Risk**: Low
**Time**: ~1h

---

### P3 — Low (future)

---

#### P3.1: Upgrade Reranker to Cohere Rerank 3.5

**Current**: BGE cross-encoder (free, local, but lower accuracy)
**Target**: Cohere Rerank 3.5 (paid, API, higher accuracy)

**Expected impact**:
- Better relevance ranking for medical queries
- Higher MRR (Mean Reciprocal Rank)
- Reduced hallucination via better top-k selection

**Time**: ~1h config change

---

#### P3.2: Query Expansion for Medical Entities

- Use LLM to expand abbreviations: "IM" → "intramuscular"
- Use LLM to generate synonyms: "exosomes" → "exosome therapy, exosome treatment"
- Hybrid search with BM25 (if Chroma adds support, or add external index)

---

#### P3.3: Multi-hop Reasoning

- For complex queries (e.g., "How is ECG performed and how much?"), use agentic loop:
  1. Decompose into sub-queries
  2. Search individually
  3. Aggregate results
- Currently: one-shot search + LLM — works for simple joins but misses complex multi-hop

---

## Implementation Order

```
Phase 1 (this week):
  ├─ P0.1: Enable cache + top_k      [1h]
  ├─ P0.2: HMS chunking                [4h]  ← biggest impact
  ├─ P0.3: Aggregation detection       [3h]
  ├─ P1.3: Threshold fix               [0.5h]
  └─ P1.4: Orphan cleanup              [2h]

Phase 2 (next week):
  ├─ P1.1: Hallucination guard         [3h]
  ├─ P1.2: Negation handling           [3h]
  └─ P2.1 Prompt improvement           [1.5h]

Phase 3 (next sprint):
  ├─ P2.2: Structured output errors    [1h]
  ├─ P2.3: MMR tuning                  [1h]
  └─ P3.x: Advanced features           [TBD]
```

**Expected result after Phase 1+2**:
- Section 5 pass rate: 75% → 92%+
- Knowledge leakage: eliminated for location/address queries
- Entity resolution: 90%+ for practitioner queries
- Aggregation: all items enumerated correctly
- Negation: basic cases handled correctly
- Determinism: same query → same answer

---

## Re-testing after Implementation

After each Phase, re-run Section 5 and compare:

| Test | Before | After P0 | After P1 | Notes |
|------|--------|----------|----------|-------|
| 5.1.4 Location | ❌ Petronas | ❌ | ✅ | Need P1.1 guard |
| 5.3.2 Address | ❌ Guidebook | ❌ | ✅ | Same — P1.1 |
| 5.4.8 ECG=EKG | ❌ Wrong | ❌ | ✅ | P1.1 |
| 5.6.3 Mark Bolmer | ❌ I don't know | ✅ | ✅ | P0.2 chunking |
| 5.6.4 Lisa specialty | ❌ Confused | ✅ | ✅ | P0.2 |
| 5.6.5 My Clinic services | ❌ I don't know | ⚠️ | ✅ | P0.3 aggregation |
| 5.7.2 DON'T use needle | ❌ Blood draw | ❌ | ✅ | P1.2 negation |
| 5.8.1 All vaccines | ⚠️ 2/3 | ✅ | ✅ | P0.3 |
| 5.8.2 Consultation cost | ❌ $50 only | ✅ | ✅ | P0.3 |
| 5.8.3 Mark Bolmer details | ❌ I don't know | ✅ | ✅ | P0.2 |
| 5.9.3 Who is Mark Bolmer | ❌ I don't know | ✅ | ✅ | P0.2 |
| 5.9.4 Clinic location | ❌ Petronas | ❌ | ✅ | P1.1 |
| 5.12.2 Order independence | ❌ Non-det | ⚠️ | ✅ | P0.1 cache |
| 5.12.3 MRI phrasing | ❌ Stale | ✅ | ✅ | P1.4 cleanup |
