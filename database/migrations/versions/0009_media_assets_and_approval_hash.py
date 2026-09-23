"""Add tenant-owned image assets and bind approval to a content/media hash."""

from __future__ import annotations

import hashlib
import json

from alembic import op
import sqlalchemy as sa


revision = "0009_media_assets_and_approval_hash"
down_revision = "0008_campaign_content_plans"
branch_labels = None
depends_on = None


def _content_hash(value: object) -> str:
    if isinstance(value, str):
        value = json.loads(value)
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "media_assets" not in inspector.get_table_names():
        op.create_table(
            "media_assets",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("company_id", sa.String(length=36), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
            sa.Column("filename", sa.String(length=255), nullable=False),
            sa.Column("mime_type", sa.String(length=100), nullable=False),
            sa.Column("size_bytes", sa.Integer(), nullable=False),
            sa.Column("content_sha256", sa.String(length=64), nullable=False),
            sa.Column("width", sa.Integer(), nullable=False),
            sa.Column("height", sa.Integer(), nullable=False),
            sa.Column("alt_text", sa.String(length=500), nullable=False, server_default=""),
            sa.Column("storage_key", sa.String(length=1024), nullable=False, unique=True),
            sa.Column("uploaded_by", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("company_id", "content_sha256", name="uq_media_asset_company_hash"),
        )
        op.create_index("ix_media_asset_company_created", "media_assets", ["company_id", "created_at"])

    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("post_approvals")}
    if "content_sha256" not in columns:
        op.add_column("post_approvals", sa.Column("content_sha256", sa.String(length=64), nullable=True))

    connection = op.get_bind()
    approvals = connection.execute(sa.text("SELECT id, post_id, version FROM post_approvals")).mappings().all()
    for approval in approvals:
        content = connection.execute(
            sa.text("SELECT content_json FROM post_versions WHERE post_id = :post_id AND version = :version"),
            {"post_id": approval["post_id"], "version": approval["version"]},
        ).scalar_one_or_none()
        if content is None:
            raise RuntimeError(f"Approval {approval['id']} has no matching immutable post version")
        connection.execute(
            sa.text("UPDATE post_approvals SET content_sha256 = :digest WHERE id = :id"),
            {"digest": _content_hash(content), "id": approval["id"]},
        )

    with op.batch_alter_table("post_approvals") as batch:
        batch.alter_column("content_sha256", existing_type=sa.String(length=64), nullable=False)


def downgrade() -> None:
    op.drop_index("ix_media_asset_company_created", table_name="media_assets")
    op.drop_table("media_assets")
    with op.batch_alter_table("post_approvals") as batch:
        batch.drop_column("content_sha256")
