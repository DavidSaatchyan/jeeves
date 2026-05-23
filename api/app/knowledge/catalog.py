"""Catalog importer — parse, textualize, and index product catalog data.

Handles CSV, XLSX, and JSON file formats.  Products are stored in both
SQL (ProductCatalog table) and Chroma (textualized for semantic search).
"""
from __future__ import annotations

import csv
import io
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from .. import rag
from ..models import ProductCatalog

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── Parsers ────────────────────────────────────────────────────────────────


def parse_csv(content: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Parse CSV string into product dicts.  First row must be column headers."""
    products: list[dict[str, Any]] = []
    errors: list[str] = []
    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames:
        return [], ["CSV has no header row"]

    for i, row in enumerate(reader, start=2):
        row = {k.strip(): v.strip() if v else "" for k, v in row.items()}
        name = row.get("name", "").strip()
        if not name:
            errors.append(f"Row {i}: missing 'name' — skipped")
            continue
        product_id = row.get("product_id", "") or row.get("sku", "")
        try:
            price_raw = row.get("price", "").strip()
            price_cents = _parse_price(price_raw)
        except ValueError as e:
            errors.append(f"Row {i}: invalid price '{row.get('price')}' — {e}")
            price_cents = None

        products.append({
            "product_id": product_id,
            "name": name,
            "description": row.get("description", ""),
            "category": row.get("category", ""),
            "price": price_cents,
            "currency": row.get("currency", "USD"),
            "attributes": _parse_attributes(row.get("attributes", "")),
            "stock_status": row.get("stock_status", "unknown"),
            "image_url": row.get("image_url", ""),
            "product_url": row.get("product_url", ""),
        })
    return products, errors


def parse_json(content: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Parse JSON string into product dicts.
    Accepts either a JSON array or an object with a ``products`` key.
    """
    errors: list[str] = []
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        return [], [f"Invalid JSON: {e}"]

    if isinstance(data, dict):
        data = data.get("products", data.get("items", [data]))
    if not isinstance(data, list):
        return [], ["JSON root must be an array or an object with a 'products' key"]

    products: list[dict[str, Any]] = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            errors.append(f"Item {i}: expected object, got {type(item).__name__}")
            continue
        name = str(item.get("name", "") or "").strip()
        if not name:
            errors.append(f"Item {i}: missing 'name' — skipped")
            continue
        price_raw = item.get("price")
        try:
            price_cents = _parse_price(str(price_raw)) if price_raw is not None else None
        except ValueError as e:
            errors.append(f"Item {i}: invalid price '{price_raw}' — {e}")
            price_cents = None

        products.append({
            "product_id": str(item.get("product_id", "") or item.get("sku", "")),
            "name": name,
            "description": str(item.get("description", "")),
            "category": str(item.get("category", "")),
            "price": price_cents,
            "currency": str(item.get("currency", "USD")),
            "attributes": item.get("attributes", {}),
            "stock_status": str(item.get("stock_status", "unknown")),
            "image_url": str(item.get("image_url", "")),
            "product_url": str(item.get("product_url", "")),
        })
    return products, errors


def parse_xlsx(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """Parse XLSX file into product dicts.  First row must be column headers."""
    try:
        import pandas as pd
    except ImportError:
        return [], ["XLSX support requires 'pandas' — install it with 'pip install pandas openpyxl'"]

    errors: list[str] = []
    try:
        df = pd.read_excel(str(path), dtype=str)
    except Exception as e:
        return [], [f"Failed to read XLSX: {e}"]

    if df.empty:
        return [], ["XLSX file is empty"]

    df = df.fillna("")
    products: list[dict[str, Any]] = []
    for i, (_, row) in enumerate(df.iterrows(), start=2):
        r = {k.strip(): str(v).strip() for k, v in row.items()}
        name = r.get("name", "")
        if not name:
            errors.append(f"Row {i}: missing 'name' — skipped")
            continue
        product_id = r.get("product_id", "") or r.get("sku", "")
        price_raw = r.get("price", "").strip()
        try:
            price_cents = _parse_price(price_raw) if price_raw else None
        except ValueError as e:
            errors.append(f"Row {i}: invalid price '{price_raw}' — {e}")
            price_cents = None

        products.append({
            "product_id": product_id,
            "name": name,
            "description": r.get("description", ""),
            "category": r.get("category", ""),
            "price": price_cents,
            "currency": r.get("currency", "USD"),
            "attributes": _parse_attributes(r.get("attributes", "")),
            "stock_status": r.get("stock_status", "unknown"),
            "image_url": r.get("image_url", ""),
            "product_url": r.get("product_url", ""),
        })
    return products, errors


def parse_catalog(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """Auto-detect format and parse.  Returns (products, errors)."""
    ext = path.suffix.lower()
    if ext == ".csv":
        return parse_csv(path.read_text(encoding="utf-8", errors="ignore"))
    elif ext == ".json":
        return parse_json(path.read_text(encoding="utf-8", errors="ignore"))
    elif ext in (".xlsx", ".xls"):
        return parse_xlsx(path)
    else:
        return [], [f"Unsupported format: {ext} (supported: .csv, .json, .xlsx)"]


# ── Helpers ────────────────────────────────────────────────────────────────


def _parse_price(raw: str) -> int | None:
    """Convert a price string to cents.  Accepts ``"29.99"`` or ``"2999"`` (already cents)."""
    raw = raw.strip().replace("$", "").replace(",", "").replace(" ", "")
    if not raw:
        return None
    val = float(raw)
    # heuristic: if value > 100 it might already be cents
    if val > 100 and "." not in raw:
        return int(val)
    return int(round(val * 100))


def _parse_attributes(raw: str) -> dict[str, Any]:
    """Parse ``"color=red, size=M"`` into ``{color: red, size: M}``."""
    if not raw or raw == "{}":
        return {}
    if raw.startswith("{") and raw.endswith("}"):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
    result: dict[str, Any] = {}
    for part in raw.split(","):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            result[k.strip()] = v.strip()
        elif ":" in part:
            k, v = part.split(":", 1)
            result[k.strip()] = v.strip()
    return result


# ── Import orchestrator ────────────────────────────────────────────────────


def import_catalog(
    tenant_id: UUID,
    path: Path,
    db: Session,
    batch: str | None = None,
) -> tuple[int, list[str], str]:
    """Parse, validate, insert into SQL, and index into Chroma.

    Returns ``(imported_count, errors, batch_id)``.
    """
    products, errors = parse_catalog(path)
    if not products and not errors:
        return 0, ["No products found in file"], ""

    batch_id = batch or _now().strftime("import_%Y%m%d_%H%M%S")

    # Insert into SQL
    imported = 0
    for p in products:
        rec = ProductCatalog(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            product_id=p["product_id"],
            name=p["name"],
            description=p.get("description", ""),
            category=p.get("category", ""),
            price=p.get("price"),
            currency=p.get("currency", "USD"),
            attributes=p.get("attributes", {}),
            stock_status=p.get("stock_status", "unknown"),
            image_url=p.get("image_url", ""),
            product_url=p.get("product_url", ""),
            import_batch=batch_id,
        )
        db.add(rec)
        imported += 1
    db.commit()
    logger.info("import_catalog: inserted %d products into SQL (batch=%s)", imported, batch_id)

    # Index into Chroma
    try:
        indexed = rag.index_products(tenant_id, products, import_batch=batch_id)
        logger.info("import_catalog: indexed %d products into Chroma", indexed)
    except Exception as e:
        logger.error("import_catalog: Chroma indexing failed: %s", e)
        errors.append(f"Chroma indexing error: {e}")

    return imported, errors, batch_id
