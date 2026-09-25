"""Add multi-Page groups and scheduled market research evidence."""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op


revision = "0012_market_research_and_page_groups"
down_revision = "0011_meta_page_integration"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def _create_table_if_missing(name: str, *columns, **kwargs) -> None:
    if not _table_exists(name):
        op.create_table(name, *columns, **kwargs)


def _index_exists(name: str, table: str) -> bool:
    return _table_exists(table) and name in {
        item["name"] for item in sa.inspect(op.get_bind()).get_indexes(table)
    }


def _create_index_if_missing(name: str, table: str, columns: list[str]) -> None:
    if not _index_exists(name, table):
        op.create_index(name, table, columns)


def _add_column_if_missing(table: str, column: sa.Column) -> None:
    existing = {item["name"] for item in sa.inspect(op.get_bind()).get_columns(table)}
    if column.name not in existing:
        if op.get_bind().dialect.name == "sqlite" and column.foreign_keys:
            with op.batch_alter_table(table, recreate="always") as batch:
                batch.add_column(column)
        else:
            op.add_column(table, column)


def _drop_index_if_exists(name: str, table: str) -> None:
    if _index_exists(name, table):
        op.drop_index(name, table_name=table)


def _drop_column_if_exists(table: str, name: str) -> None:
    existing = {item["name"] for item in sa.inspect(op.get_bind()).get_columns(table)}
    if name in existing:
        if op.get_bind().dialect.name == "sqlite":
            with op.batch_alter_table(
                table,
                recreate="always",
                naming_convention={"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"},
            ) as batch:
                batch.drop_column(name)
        else:
            op.drop_column(table, name)


def _drop_table_if_exists(name: str) -> None:
    if _table_exists(name):
        op.drop_table(name)


def upgrade() -> None:
    _create_table_if_missing(
        "meta_page_groups",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("company_id", sa.String(36), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("industry", sa.String(160), nullable=False),
        sa.Column("region", sa.String(160), nullable=False),
        sa.Column("locale", sa.String(24), nullable=False, server_default="vi-VN"),
        sa.Column("keywords_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("next_due_at", sa.DateTime(timezone=True)),
        sa.Column("last_cycle_at", sa.DateTime(timezone=True)),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("company_id", "name", name="uq_meta_page_group_name"),
    )
    _create_index_if_missing("ix_meta_page_groups_company_id", "meta_page_groups", ["company_id"])
    _create_index_if_missing("ix_meta_page_groups_next_due_at", "meta_page_groups", ["next_due_at"])

    now = sa.func.now()
    bind = op.get_bind()
    companies = bind.execute(sa.text("SELECT id, industry FROM companies")).mappings().all()
    group_by_company: dict[str, str] = {}
    for company in companies:
        existing_group_id = bind.execute(
            sa.text("SELECT id FROM meta_page_groups WHERE company_id = :company_id AND name = :name"),
            {"company_id": str(company["id"]), "name": "Mặc định"},
        ).scalar_one_or_none()
        if existing_group_id:
            group_by_company[str(company["id"])] = str(existing_group_id)
            continue
        group_id = str(uuid.uuid4())
        group_by_company[str(company["id"])] = group_id
        bind.execute(
            sa.text(
                "INSERT INTO meta_page_groups "
                "(id, company_id, name, industry, region, locale, keywords_json, active, created_at, updated_at) "
                "VALUES (:id, :company_id, :name, :industry, :region, :locale, :keywords, :active, :created_at, :updated_at)"
            ),
            {
                "id": group_id,
                "company_id": str(company["id"]),
                "name": "Mặc định",
                "industry": company["industry"] or "Chưa khai báo",
                "region": "Việt Nam",
                "locale": "vi-VN",
                "keywords": "[]",
                "active": True,
                "created_at": bind.execute(sa.select(now)).scalar_one(),
                "updated_at": bind.execute(sa.select(now)).scalar_one(),
            },
        )

    _create_table_if_missing(
        "meta_page_connections",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("company_id", sa.String(36), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("group_id", sa.String(36), sa.ForeignKey("meta_page_groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("page_id", sa.String(100), nullable=False),
        sa.Column("page_name", sa.String(200)),
        sa.Column("encrypted_token", sa.Text(), nullable=False),
        sa.Column("token_fingerprint", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="configured"),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column("last_error_code", sa.String(80)),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("company_id", "page_id", name="uq_meta_connection_company_page"),
    )
    _create_index_if_missing("ix_meta_page_connections_company_id", "meta_page_connections", ["company_id"])
    _create_index_if_missing("ix_meta_connection_group_active", "meta_page_connections", ["company_id", "group_id", "active"])
    _add_column_if_missing("meta_publications", sa.Column("connection_id", sa.String(36), sa.ForeignKey("meta_page_connections.id", ondelete="SET NULL", name="fk_meta_publications_connection_id")))
    _create_index_if_missing("ix_meta_publications_connection_id", "meta_publications", ["connection_id"])

    _add_column_if_missing("campaigns", sa.Column("group_id", sa.String(36), sa.ForeignKey("meta_page_groups.id", ondelete="SET NULL", name="fk_campaigns_group_id")))
    _create_index_if_missing("ix_campaigns_group_id", "campaigns", ["group_id"])
    _add_column_if_missing("campaign_posts", sa.Column("target_connection_id", sa.String(36), sa.ForeignKey("meta_page_connections.id", ondelete="SET NULL", name="fk_campaign_posts_target_connection_id")))

    _create_table_if_missing(
        "research_sources",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("company_id", sa.String(36), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("group_id", sa.String(36), sa.ForeignKey("meta_page_groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("connection_id", sa.String(36), sa.ForeignKey("meta_page_connections.id", ondelete="SET NULL")),
        sa.Column("source_type", sa.String(40), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("normalized_url", sa.String(2048), nullable=False),
        sa.Column("competitor_name", sa.String(200)),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("next_due_at", sa.DateTime(timezone=True)),
        sa.Column("last_crawled_at", sa.DateTime(timezone=True)),
        sa.Column("latest_job_id", sa.String(36), sa.ForeignKey("jobs.id", ondelete="SET NULL")),
        sa.Column("error_json", sa.JSON()),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("company_id", "group_id", "normalized_url", name="uq_research_source_url"),
    )
    _create_index_if_missing("ix_research_sources_company_id", "research_sources", ["company_id"])
    _create_index_if_missing("ix_research_sources_group_id", "research_sources", ["group_id"])
    _create_index_if_missing("ix_research_sources_next_due_at", "research_sources", ["next_due_at"])
    _create_index_if_missing("ix_research_source_due", "research_sources", ["company_id", "group_id", "active", "next_due_at"])

    _create_table_if_missing(
        "research_cycles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("company_id", sa.String(36), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("group_id", sa.String(36), sa.ForeignKey("meta_page_groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("cycle_key", sa.String(100), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="queued"),
        sa.Column("source_results_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("report_id", sa.String(36)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("company_id", "group_id", "cycle_key", name="uq_research_cycle_window"),
    )
    _create_index_if_missing("ix_research_cycle_group_created", "research_cycles", ["company_id", "group_id", "created_at"])

    _create_table_if_missing(
        "market_evidence",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("company_id", sa.String(36), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("group_id", sa.String(36), sa.ForeignKey("meta_page_groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_id", sa.String(36), sa.ForeignKey("research_sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("canonical_url", sa.String(2048), nullable=False),
        sa.Column("external_id", sa.String(255)),
        sa.Column("title", sa.String(1000), nullable=False, server_default=""),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("trust_level", sa.String(32), nullable=False, server_default="external_unverified"),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("company_id", "source_id", "canonical_url", name="uq_market_evidence_source_url"),
    )
    _create_index_if_missing("ix_market_evidence_group_published", "market_evidence", ["company_id", "group_id", "published_at"])

    _create_table_if_missing(
        "market_observations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("company_id", sa.String(36), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("evidence_id", sa.String(36), sa.ForeignKey("market_evidence.id", ondelete="CASCADE"), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metrics_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("comments_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("raw_object_key", sa.String(1024)),
        sa.Column("raw_sha256", sa.String(64)),
        sa.Column("raw_expires_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("evidence_id", "observed_at", name="uq_market_observation_at"),
    )
    _create_index_if_missing("ix_market_observation_evidence_at", "market_observations", ["evidence_id", "observed_at"])
    _create_index_if_missing("ix_market_observations_raw_expires_at", "market_observations", ["raw_expires_at"])

    _create_table_if_missing(
        "market_reports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("company_id", sa.String(36), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("group_id", sa.String(36), sa.ForeignKey("meta_page_groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cycle_id", sa.String(36), sa.ForeignKey("research_cycles.id", ondelete="SET NULL")),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("report_json", sa.JSON(), nullable=False),
        sa.Column("evidence_ids_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("coverage_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("model_name", sa.String(160)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    _create_index_if_missing("ix_market_report_group_created", "market_reports", ["company_id", "group_id", "created_at"])

    # Preserve the existing pilot's connection as a configurable connection if
    # it belongs to a workspace already present at migration time.
    # The encrypted row itself is created later by the authenticated owner UI.


def downgrade() -> None:
    for name, table in (
        ("ix_market_report_group_created", "market_reports"),
        ("ix_market_observations_raw_expires_at", "market_observations"),
        ("ix_market_observation_evidence_at", "market_observations"),
        ("ix_market_evidence_group_published", "market_evidence"),
        ("ix_research_cycle_group_created", "research_cycles"),
        ("ix_research_source_due", "research_sources"),
        ("ix_research_sources_group_id", "research_sources"),
        ("ix_research_sources_company_id", "research_sources"),
        ("ix_research_sources_next_due_at", "research_sources"),
    ):
        _drop_index_if_exists(name, table)
    for table in ("market_reports", "market_observations", "market_evidence", "research_cycles", "research_sources"):
        _drop_table_if_exists(table)

    _drop_column_if_exists("campaign_posts", "target_connection_id")
    _drop_index_if_exists("ix_meta_publications_connection_id", "meta_publications")
    _drop_column_if_exists("meta_publications", "connection_id")
    _drop_index_if_exists("ix_meta_connection_group_active", "meta_page_connections")
    _drop_index_if_exists("ix_meta_page_connections_company_id", "meta_page_connections")
    _drop_table_if_exists("meta_page_connections")
    _drop_index_if_exists("ix_campaigns_group_id", "campaigns")
    _drop_column_if_exists("campaigns", "group_id")
    _drop_index_if_exists("ix_meta_page_groups_next_due_at", "meta_page_groups")
    _drop_index_if_exists("ix_meta_page_groups_company_id", "meta_page_groups")
    _drop_table_if_exists("meta_page_groups")
