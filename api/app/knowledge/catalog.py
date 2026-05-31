"""Catalog importer — stub (product catalog feature removed in Phase 1 refactor)."""
from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session


def import_catalog(
    tenant_id: UUID,
    path: Path,
    db: Session,
    batch: str | None = None,
) -> tuple[int, list[str], str]:
    return 0, ["Catalog import disabled"], ""


def parse_catalog(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    return [], []
