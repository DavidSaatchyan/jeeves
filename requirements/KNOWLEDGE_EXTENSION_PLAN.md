# Knowledge Base Extension Plan

## Current Architecture

```
FileRecord (SQL)              ChromaDB (vector store)
┌──────────────────┐          ┌──────────────────────┐
│ id               │          │ collection: tenant_xxx│
│ tenant_id        │          │ - document chunks     │
│ filename         │          │ - metadata: file_id,  │
│ content_hash     │          │   filename, section,  │
│ status           │          │   page, chunk_hash    │
│ chunks_total     │          └──────────────────────┘
│ size_bytes       │         
└──────────────────┘         
```

- **Один** тип данных: документы (.txt, .pdf, .md)
- Все чанки — в одной Chroma-коллекции, без дискриминации по типу
- Нет структурированных данных — нет SQL-моделей для товаров, нет точного поиска по SKU/цене/наличию
- `rag.search()` — только семантический поиск, нет фильтрации по типу

---

## Target Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Query Router                       │
│  User question → intent detection → dispatch         │
└────────┬────────────┬──────────────────┬────────────┘
         │            │                  │
         ▼            ▼                  ▼
   Chroma search   SQL exact lookup   Compatibility
   (semantic)      (SKU, stock,       matching
   type=all|        price, category)   (model→model)
   catalog|doc                         
         │            │                  │
         └────────────┴──────────────────┘
                        ▼
              Enriched context → LLM → answer
```

### New SQL Models

```python
class ProductCatalog(Base):
    """Structured product data — single source of truth for catalog."""
    __tablename__ = "product_catalog"
    # product_id (external: SKU/Shopify ID), name, description, category,
    # price, currency, attributes (JSONB), stock_status, image_url,
    # product_url, active, import_batch, created_at, updated_at

class CatalogVariant(Base):
    """Product variants (sizes, colors)."""
    __tablename__ = "catalog_variants"
    # product_id → ProductCatalog, sku, name, attributes (JSONB),
    # price, stock_status

class Compatibility(Base):
    """Compatibility tables — model A ↔ model B relationships."""
    __tablename__ = "compatibility"
    # source_product_id, target_product_id, relationship (compatible_with,
    # requires, optional_for), condition, notes

# Extended FileRecord
file_type: str             # "document" | "catalog" | "compatibility"
metadata_schema: JSONB     # CSV column mapping for structured imports
```

### Search Strategy

```python
# rag.search() — новый параметр type
def search(tenant_id, query, top_k=15, threshold=0.75, type=None):
    """type: None=all, 'document', 'catalog', 'compatibility'"""

# Новый: ProductCatalog SQL lookup
def lookup_product(tenant_id, sku=None, category=None, in_stock=None):

# Новый: Compatibility exact match
def lookup_compatibility(tenant_id, model_name):
```

### Chat Flow (Enhanced)

```
1. rag.search(type='catalog') → semantic product matches
2. Extract product_ids → SQL lookup for live stock/price
3. rag.search(type='document') → policies, FAQs
4. If compatibility query → Compatibility.lookup(model)
5. Merge contexts → LLM
```

### Import Pipeline

```
CSV/XLSX/JSON → Schema Mapper → Parser → SQL INSERT ProductCatalog
  → Textualizer (row → text block) → chunking → embed → Chroma (type=catalog)
```

---

## Implementation Phases

### ✅ Phase 0 — Data Models (DONE)

| Task | Files | Status |
|------|-------|--------|
| Add `ProductCatalog`, `CatalogVariant`, `Compatibility` models | `models.py` | ✅ |
| Extend `FileRecord` with `file_type`, `metadata_schema` | `models.py` | ✅ |
| Add Pydantic schemas | `schemas.py` | ✅ |
| Create Alembic migration | `alembic/versions/` | ✅ |

### 🔲 Phase 1 — Catalog Importer

| Task | Files |
|------|-------|
| CSV parser with column mapping | `knowledge/catalog.py` |
| XLSX parser | `knowledge/catalog.py` |
| JSON parser (Shopify format) | `knowledge/catalog.py` |
| Textualizer: product row → searchable text | `knowledge/catalog.py` |
| `rag.index_products()` — batch index with type metadata | `rag.py` |
| `rag.search()` — type filter support | `rag.py` |
| Add `openpyxl` to requirements | `requirements.txt` |

### 🔲 Phase 2 — Catalog API + Search

| Task | Files |
|------|-------|
| `POST /knowledge/catalog/upload` | `knowledge.py` |
| `GET /knowledge/catalog` (list) | `knowledge.py` |
| `GET /knowledge/catalog/search?q=...` | `knowledge.py` |
| `DELETE /knowledge/catalog/{id}` | `knowledge.py` |
| `rag.search_structured()` — hybrid Chroma + SQL | `rag.py` |

### 🔲 Phase 3 — Compatibility Module

| Task | Files |
|------|-------|
| `parse_compatibility_csv()` | `knowledge/compatibility.py` |
| `textualize_compatibility_row()` | `knowledge/compatibility.py` |
| `rag.index_compatibility()` | `rag.py` |
| Endpoints: upload, search by model | `knowledge.py` |

### 🔲 Phase 4 — Chat Integration

| Task | Files |
|------|-------|
| `rag.hybrid_search()` — unifies semantic + exact | `rag.py` |
| Update `/knowledge/chat` to use hybrid search | `knowledge.py` |
| Update widget chat to include catalog search | `channels/widget.py` |

### 🔲 Phase 5 — UI + API Sync (post-MVP)

| Task |
|------|
| Admin UI: catalog upload, browse, search |
| Schema mapping UI (drag-drop CSV columns → model fields) |
| Shopify API connector (`integrations/shopify.py`) |
| Periodic sync worker |
