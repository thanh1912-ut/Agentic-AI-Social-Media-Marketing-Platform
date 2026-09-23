"""Allow multiple pinned embedding models without discarding old vectors."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector


revision = "0010_flexible_embedding_dimensions"
down_revision = "0009_media_assets_and_approval_hash"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        # SQLite stores the test representation as JSON, which already accepts
        # vectors of different lengths.
        return
    op.alter_column(
        "knowledge_chunks",
        "embedding",
        existing_type=Vector(1536),
        type_=Vector(),
        postgresql_using="embedding::vector",
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    incompatible = op.get_bind().execute(
        sa.text(
            "SELECT count(*) FROM knowledge_chunks "
            "WHERE embedding IS NOT NULL AND vector_dims(embedding) <> 1536"
        )
    ).scalar_one()
    if incompatible:
        raise RuntimeError(
            "Cannot downgrade embeddings to vector(1536) while non-1536 vectors exist; reindex or remove them first"
        )
    op.alter_column(
        "knowledge_chunks",
        "embedding",
        existing_type=Vector(),
        type_=Vector(1536),
        postgresql_using="embedding::vector(1536)",
    )
