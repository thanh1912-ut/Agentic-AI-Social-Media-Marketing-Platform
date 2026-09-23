"""Track retrieval mode and versioned knowledge-index identity."""

from alembic import op
import sqlalchemy as sa


revision = "0003_deepseek_knowledge_versions"
down_revision = "0002_profile_knowledge"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    current = {
        table: {column["name"] for column in inspector.get_columns(table)}
        for table in ("documents", "knowledge_chunks")
    }
    additions = {
        "documents": {
            "retrieval_mode": sa.Column(
                "retrieval_mode", sa.String(length=30), nullable=False, server_default="not_available"
            ),
        },
        "knowledge_chunks": {
            "parser_version": sa.Column("parser_version", sa.String(length=40), nullable=False, server_default="legacy"),
            "chunker_version": sa.Column("chunker_version", sa.String(length=80), nullable=False, server_default="legacy"),
            "embedding_provider": sa.Column("embedding_provider", sa.String(length=40), nullable=False, server_default="legacy"),
            "embedding_model_version": sa.Column("embedding_model_version", sa.String(length=160), nullable=False, server_default="legacy"),
        },
    }
    for table, columns in additions.items():
        for name, column in columns.items():
            if name not in current[table]:
                op.add_column(table, column)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    current = {
        table: {column["name"] for column in inspector.get_columns(table)}
        for table in ("documents", "knowledge_chunks")
    }
    for name in ("embedding_model_version", "embedding_provider", "chunker_version", "parser_version"):
        if name in current["knowledge_chunks"]:
            op.drop_column("knowledge_chunks", name)
    if "retrieval_mode" in current["documents"]:
        op.drop_column("documents", "retrieval_mode")
