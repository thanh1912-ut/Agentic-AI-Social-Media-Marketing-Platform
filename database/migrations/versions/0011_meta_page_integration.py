"""Persist guarded Meta publications and historical Page metrics."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0011_meta_page_integration"
down_revision = "0010_flexible_embedding_dimensions"
branch_labels = None
depends_on = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def _table_exists(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def _create_table_if_missing(name: str, *columns, **kwargs) -> None:
    if not _table_exists(name):
        op.create_table(name, *columns, **kwargs)


def _create_index_if_missing(name: str, table: str, columns: list[str]) -> None:
    existing = {item["name"] for item in sa.inspect(op.get_bind()).get_indexes(table)}
    if name not in existing:
        op.create_index(name, table, columns)


def upgrade() -> None:
    _create_table_if_missing(
        "meta_publications",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("company_id", sa.String(36), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("post_id", sa.String(36), sa.ForeignKey("campaign_posts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("post_version", sa.Integer(), nullable=False),
        sa.Column("approved_content_sha256", sa.String(64), nullable=False),
        sa.Column("page_id", sa.String(100), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("active_key", sa.String(255)),
        sa.Column("external_post_id", sa.String(160)),
        sa.Column("permalink", sa.String(2048)),
        sa.Column("error_json", sa.JSON()),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("jobs.id"), nullable=False, unique=True),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        *_timestamps(),
        sa.UniqueConstraint("company_id", "active_key", name="uq_meta_publication_active"),
    )
    _create_index_if_missing("ix_meta_publication_company_created", "meta_publications", ["company_id", "created_at"])
    _create_table_if_missing(
        "meta_page_posts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("company_id", sa.String(36), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("page_id", sa.String(100), nullable=False),
        sa.Column("external_post_id", sa.String(160), nullable=False),
        sa.Column("linked_post_id", sa.String(36), sa.ForeignKey("campaign_posts.id", ondelete="SET NULL")),
        sa.Column("message", sa.Text()),
        sa.Column("permalink", sa.String(2048)),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("reactions", sa.Integer()),
        sa.Column("comments", sa.Integer()),
        sa.Column("shares", sa.Integer()),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("company_id", "page_id", "external_post_id", name="uq_meta_page_post_external"),
    )
    _create_index_if_missing("ix_meta_page_post_company_published", "meta_page_posts", ["company_id", "published_at"])
    _create_table_if_missing(
        "meta_sync_states",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("company_id", sa.String(36), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("page_id", sa.String(100), nullable=False),
        sa.Column("page_name", sa.String(200)),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column("next_cursor", sa.Text()),
        sa.Column("has_more", sa.Boolean(), nullable=False),
        sa.Column("last_sync_at", sa.DateTime(timezone=True)),
        sa.Column("running_job_id", sa.String(36), sa.ForeignKey("jobs.id", ondelete="SET NULL")),
        *_timestamps(),
        sa.UniqueConstraint("company_id", "page_id", name="uq_meta_sync_company_page"),
    )


def downgrade() -> None:
    op.drop_table("meta_sync_states")
    op.drop_index("ix_meta_page_post_company_published", table_name="meta_page_posts")
    op.drop_table("meta_page_posts")
    op.drop_index("ix_meta_publication_company_created", table_name="meta_publications")
    op.drop_table("meta_publications")
