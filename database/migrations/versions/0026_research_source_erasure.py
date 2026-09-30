"""Add durable source-scoped research data purge requests."""

from alembic import op
import sqlalchemy as sa


revision = "0026_research_source_erasure"
down_revision = "0025_owned_page_research_backfill"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "market_observations" in tables:
        columns = {item["name"] for item in inspector.get_columns("market_observations")}
        if "raw_upload_lease_until" not in columns:
            op.add_column(
                "market_observations",
                sa.Column("raw_upload_lease_until", sa.DateTime(timezone=True), nullable=True),
            )

    if "research_source_erasures" not in tables:
        op.create_table(
            "research_source_erasures",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("company_id", sa.String(length=36), nullable=False),
            sa.Column("source_id", sa.String(length=36), nullable=False),
            sa.Column("job_id", sa.String(length=36), nullable=False),
            sa.Column("requested_by", sa.String(length=36), nullable=False),
            sa.Column("status", sa.String(length=32), server_default="queued", nullable=False),
            sa.Column("object_count", sa.Integer(), server_default="0", nullable=False),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("error_code", sa.String(length=80), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["requested_by"], ["users.id"]),
            sa.ForeignKeyConstraint(
                ["company_id", "source_id"], ["research_sources.company_id", "research_sources.id"],
                name="fk_research_source_erasure_source_tenant",
            ),
            sa.ForeignKeyConstraint(
                ["company_id", "job_id"], ["jobs.company_id", "jobs.id"],
                name="fk_research_source_erasure_job_tenant", ondelete="CASCADE",
            ),
            sa.UniqueConstraint("company_id", "source_id", name="uq_research_source_erasure_source"),
            sa.UniqueConstraint("company_id", "id", name="uq_research_source_erasure_tenant_id"),
            sa.UniqueConstraint("company_id", "job_id", name="uq_research_source_erasure_job"),
        )
        op.create_index(
            "ix_research_source_erasure_status",
            "research_source_erasures", ["status", "created_at"],
        )

    if "research_source_erasure_objects" not in tables:
        op.create_table(
            "research_source_erasure_objects",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("company_id", sa.String(length=36), nullable=False),
            sa.Column("erasure_id", sa.String(length=36), nullable=False),
            sa.Column("object_key", sa.String(length=1024), nullable=False),
            sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(
                ["company_id", "erasure_id"],
                ["research_source_erasures.company_id", "research_source_erasures.id"],
                name="fk_research_source_erasure_object_tenant", ondelete="CASCADE",
            ),
            sa.UniqueConstraint(
                "company_id", "erasure_id", "object_key",
                name="uq_research_source_erasure_object_key",
            ),
        )
        op.create_index(
            "ix_research_source_erasure_object_status",
            "research_source_erasure_objects", ["company_id", "erasure_id", "status"],
        )


def downgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "research_source_erasure_objects" in tables:
        op.drop_index("ix_research_source_erasure_object_status", table_name="research_source_erasure_objects")
        op.drop_table("research_source_erasure_objects")
    if "research_source_erasures" in tables:
        op.drop_index("ix_research_source_erasure_status", table_name="research_source_erasures")
        op.drop_table("research_source_erasures")
    if "market_observations" in tables:
        columns = {item["name"] for item in sa.inspect(op.get_bind()).get_columns("market_observations")}
        if "raw_upload_lease_until" in columns:
            op.drop_column("market_observations", "raw_upload_lease_until")
