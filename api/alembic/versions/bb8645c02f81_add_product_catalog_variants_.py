"""add product_catalog, catalog_variants, compatibility tables

Revision ID: bb8645c02f81
Revises: 5a6b7c8d9e0f
Create Date: 2026-05-23 12:27:24.272914

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "bb8645c02f81"
down_revision: Union[str, Sequence[str], None] = "5a6b7c8d9e0f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- FileRecord extension ---
    op.add_column("files", sa.Column("file_type", sa.String(32), server_default="document", nullable=False))
    op.add_column("files", sa.Column("metadata_schema", sa.JSON(), nullable=True))

    # --- ProductCatalog ---
    op.create_table(
        "product_catalog",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), server_default=""),
        sa.Column("category", sa.Text(), server_default=""),
        sa.Column("price", sa.Integer(), nullable=True),
        sa.Column("currency", sa.String(8), server_default="USD"),
        sa.Column("attributes", sa.JSON(), server_default=sa.text("'{}'::json")),
        sa.Column("stock_status", sa.String(16), server_default="unknown"),
        sa.Column("image_url", sa.Text(), server_default=""),
        sa.Column("product_url", sa.Text(), server_default=""),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("import_batch", sa.Text(), server_default=""),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_product_catalog_tenant_id"), "product_catalog", ["tenant_id"])

    # --- CatalogVariant ---
    op.create_table(
        "catalog_variants",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", UUID(as_uuid=True), sa.ForeignKey("product_catalog.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sku", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), server_default=""),
        sa.Column("attributes", sa.JSON(), server_default=sa.text("'{}'::json")),
        sa.Column("price", sa.Integer(), nullable=True),
        sa.Column("stock_status", sa.String(16), server_default="unknown"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_catalog_variants_tenant_id"), "catalog_variants", ["tenant_id"])
    op.create_index(op.f("ix_catalog_variants_product_id"), "catalog_variants", ["product_id"])

    # --- Compatibility ---
    op.create_table(
        "compatibility",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_product_id", sa.Text(), nullable=False),
        sa.Column("source_product_name", sa.Text(), server_default=""),
        sa.Column("target_product_id", sa.Text(), nullable=False),
        sa.Column("target_product_name", sa.Text(), server_default=""),
        sa.Column("relationship", sa.String(32), server_default="compatible_with"),
        sa.Column("condition", sa.Text(), server_default=""),
        sa.Column("notes", sa.Text(), server_default=""),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_compatibility_tenant_id"), "compatibility", ["tenant_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_compatibility_tenant_id"), table_name="compatibility")
    op.drop_table("compatibility")
    op.drop_index(op.f("ix_catalog_variants_product_id"), table_name="catalog_variants")
    op.drop_index(op.f("ix_catalog_variants_tenant_id"), table_name="catalog_variants")
    op.drop_table("catalog_variants")
    op.drop_index(op.f("ix_product_catalog_tenant_id"), table_name="product_catalog")
    op.drop_table("product_catalog")
    op.drop_column("files", "metadata_schema")
    op.drop_column("files", "file_type")
