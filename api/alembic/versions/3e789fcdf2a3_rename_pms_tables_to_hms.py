"""rename pms_* tables to hms_*, migrate Chroma source from "pms" to "hms"

Renames: pms_services → hms_services, pms_practitioners → hms_practitioners,
pms_clinic → hms_clinic. Also updates existing Chroma metadata records from
source="pms" to source="hms" (one-time data migration).
"""

from __future__ import annotations

import logging
from typing import Sequence, Union

from alembic import op

logger = logging.getLogger("jeeves.migration")


revision: str = "3e789fcdf2a3"
down_revision: Union[str, Sequence[str], None] = "e7f8a0b1c2d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _migrate_chroma_source() -> None:
    """Update all Chroma metadata records from source='pms' to source='hms'.

    Runs inside the Alembic migration. Uses the app's Chroma client.
    This is a one-time migration; on subsequent startups there will be no
    source='pms' records to update, so it's effectively idempotent.
    """
    try:
        from app.db import SessionLocal
        from app.models import Tenant
        from app.rag.client import _collection
        from sqlalchemy import select

        db = SessionLocal()
        try:
            tenants = db.execute(select(Tenant).where(Tenant.is_active)).scalars().all()
            for tenant in tenants:
                try:
                    col = _collection(tenant.id)
                    result = col.get(where={"source": "pms"}, include=["metadatas"])
                    if not result or not result.get("ids"):
                        continue
                    ids = result["ids"]
                    metadatas = result.get("metadatas", [None] * len(ids))
                    updated = []
                    for m in metadatas:
                        if m and m.get("source") == "pms":
                            m["source"] = "hms"
                            updated.append(m)
                    if updated:
                        col.update(ids=ids, metadatas=updated)
                        logger.info(
                            "migrated %d Chroma records from source=pms to source=hms for tenant %s",
                            len(ids), tenant.id,
                        )
                except Exception as e:
                    logger.warning("Chroma migration skipped for tenant %s: %s", tenant.id, e)
        finally:
            db.close()
    except Exception as e:
        logger.warning("Chroma source migration skipped (Chroma not available): %s", e)


def upgrade() -> None:
    # Rename SQL tables
    op.rename_table("pms_services", "hms_services")
    op.rename_table("pms_practitioners", "hms_practitioners")
    op.rename_table("pms_clinic", "hms_clinic")
    # Rename tenant_id indexes (PostgreSQL; SQLite handles via rename_table)
    for old, new in (
        ("ix_pms_services_tenant_id", "ix_hms_services_tenant_id"),
        ("ix_pms_practitioners_tenant_id", "ix_hms_practitioners_tenant_id"),
        ("ix_pms_clinic_tenant_id", "ix_hms_clinic_tenant_id"),
    ):
        try:
            op.execute(f"ALTER INDEX {old} RENAME TO {new}")
        except Exception:
            logger.info("Index rename %s → %s not supported (SQLite?), skipping", old, new)

    # Migrate Chroma metadata source from "pms" to "hms"
    _migrate_chroma_source()


def downgrade() -> None:
    # Rename indexes back (PostgreSQL)
    for old, new in (
        ("ix_hms_services_tenant_id", "ix_pms_services_tenant_id"),
        ("ix_hms_practitioners_tenant_id", "ix_pms_practitioners_tenant_id"),
        ("ix_hms_clinic_tenant_id", "ix_pms_clinic_tenant_id"),
    ):
        try:
            op.execute(f"ALTER INDEX {old} RENAME TO {new}")
        except Exception:
            pass
    # Rename tables back
    op.rename_table("hms_services", "pms_services")
    op.rename_table("hms_practitioners", "pms_practitioners")
    op.rename_table("hms_clinic", "pms_clinic")
