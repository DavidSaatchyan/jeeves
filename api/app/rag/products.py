from __future__ import annotations

import hashlib
import logging
from typing import Any
from uuid import UUID

from .client import _collection, embed_batch

logger = logging.getLogger(__name__)


def _textualize_product(p: dict[str, Any]) -> str:
    parts = [f"Product: {p.get('name', '')}"]
    if p.get("product_id"):
        parts.append(f"SKU/ID: {p['product_id']}")
    if p.get("category"):
        parts.append(f"Category: {p['category']}")
    if p.get("price") is not None:
        currency = p.get("currency", "USD")
        price_dollars = float(p["price"]) / 100 if isinstance(p["price"], int) else float(p["price"])
        parts.append(f"Price: {price_dollars:.2f} {currency}")
    if p.get("description"):
        parts.append(f"Description: {p['description']}")
    if p.get("attributes"):
        attrs = p["attributes"]
        if isinstance(attrs, dict):
            attr_str = ", ".join(f"{k}={v}" for k, v in attrs.items())
            parts.append(f"Attributes: {attr_str}")
    if p.get("stock_status"):
        parts.append(f"Stock: {p['stock_status']}")
    if p.get("image_url"):
        parts.append(f"Image: {p['image_url']}")
    if p.get("product_url"):
        parts.append(f"URL: {p['product_url']}")
    return "\n".join(parts)


def index_products(
    tenant_id: UUID | str,
    products: list[dict[str, Any]],
    import_batch: str = "",
) -> int:
    if not products:
        return 0

    col = _collection(tenant_id)

    if import_batch:
        try:
            col.delete(where={"$and": [{"type": "product"}, {"import_batch": import_batch}]})
        except Exception:
            pass

    texts: list[str] = []
    metadatas: list[dict] = []
    ids: list[str] = []

    for i, p in enumerate(products):
        text = _textualize_product(p)
        pid = str(p.get("product_id", "") or p.get("id", "") or f"unknown-{i}")
        chunk_id = f"product-{import_batch}-{pid}" if import_batch else f"product-{pid}"
        texts.append(text)
        metadatas.append({
            "type": "product",
            "product_id": pid,
            "name": str(p.get("name", "")),
            "category": str(p.get("category", "")),
            "price": str(p["price"]) if p.get("price") is not None else "",
            "stock_status": str(p.get("stock_status", "unknown")),
            "import_batch": import_batch,
            "file_id": f"catalog-{import_batch}" if import_batch else "catalog",
            "filename": f"catalog-{import_batch}.csv" if import_batch else "catalog.json",
            "section": "Catalog",
            "chunk_hash": hashlib.sha1(text.encode("utf-8")).hexdigest()[:16],
            "char_start": 0,
            "char_end": len(text),
        })
        ids.append(chunk_id)

    embeddings = embed_batch(texts)
    col.add(ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas)
    logger.info("index_products: indexed %d products (batch=%s)", len(products), import_batch)
    return len(products)


def delete_products_by_batch(tenant_id: UUID | str, import_batch: str) -> int:
    try:
        col = _collection(tenant_id)
        before = col.count()
        col.delete(where={"$and": [{"type": "product"}, {"import_batch": import_batch}]})
        after = col.count()
        removed = before - after
        logger.info("delete_products_by_batch: batch=%s removed=%d", import_batch, removed)
        return removed
    except Exception as e:
        logger.error("delete_products_by_batch failed: %s", e)
        return 0
