"""Persist profile revisions and active, tenant-scoped knowledge chunks."""

from alembic import op
import sqlalchemy as sa

from database.models import Base


revision = "0002_profile_knowledge"
down_revision = "0001_backend_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    document_columns = {column["name"] for column in inspector.get_columns("documents")}
    if "source_id" not in document_columns:
        op.add_column("documents", sa.Column("source_id", sa.String(length=36), nullable=True))
        op.execute("UPDATE documents SET source_id = id WHERE source_id IS NULL")
        if bind.dialect.name != "sqlite":
            op.alter_column("documents", "source_id", nullable=False)
    if "source_version" not in document_columns:
        op.add_column(
            "documents",
            sa.Column("source_version", sa.String(length=40), nullable=False, server_default="1"),
        )
    if "is_active" not in document_columns:
        op.add_column(
            "documents",
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        )
    if "deleted_at" not in document_columns:
        op.add_column("documents", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    if "normalized_json" not in document_columns:
        op.add_column("documents", sa.Column("normalized_json", sa.JSON(), nullable=True))
    if "knowledge_status" not in document_columns:
        op.add_column(
            "documents",
            sa.Column("knowledge_status", sa.String(length=30), nullable=False, server_default="pending"),
        )
    if "profile_status" not in document_columns:
        op.add_column(
            "documents",
            sa.Column("profile_status", sa.String(length=30), nullable=False, server_default="pending"),
        )

    Base.metadata.create_all(bind=bind, checkfirst=True)
    inspector = sa.inspect(bind)
    indexes = {index["name"] for index in inspector.get_indexes("documents")}
    if "ix_documents_source_id" not in indexes:
        op.create_index("ix_documents_source_id", "documents", ["source_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "knowledge_chunks" in tables:
        op.drop_table("knowledge_chunks")
    if "brand_profile_revisions" in tables:
        op.drop_table("brand_profile_revisions")
    columns = {column["name"] for column in sa.inspect(bind).get_columns("documents")}
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("documents")}
    if "ix_documents_source_id" in indexes:
        op.drop_index("ix_documents_source_id", table_name="documents")
    for name in (
        "profile_status",
        "knowledge_status",
        "normalized_json",
        "deleted_at",
        "is_active",
        "source_version",
        "source_id",
    ):
        if name in columns:
            op.drop_column("documents", name)
