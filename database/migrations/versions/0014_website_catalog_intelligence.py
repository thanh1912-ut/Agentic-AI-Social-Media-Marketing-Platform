"""Store normalized website entities, offers, and crawl checkpoints."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0014_website_catalog_intelligence"
down_revision = "0013_metric_history_and_tenant_integrity"
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def _table_exists(name: str) -> bool:
    return name in _inspector().get_table_names()


def _column_exists(table: str, name: str) -> bool:
    return _table_exists(table) and name in {column["name"] for column in _inspector().get_columns(table)}


def _has_unique(table: str, name: str) -> bool:
    return _table_exists(table) and name in {item.get("name") for item in _inspector().get_unique_constraints(table)}


def _add_unique(table: str, name: str, columns: list[str]) -> None:
    if not _has_unique(table, name):
        with op.batch_alter_table(table) as batch:
            batch.create_unique_constraint(name, columns)


def _add_column(table: str, column: sa.Column) -> None:
    if _column_exists(table, column.name):
        return
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table(table) as batch:
            batch.add_column(column)
    else:
        op.add_column(table, column)


def _create_table_if_missing(name: str, *args, **kwargs) -> None:
    if not _table_exists(name):
        op.create_table(name, *args, **kwargs)


def _create_index_if_missing(name: str, table: str, columns: list[str]) -> None:
    indexes = {item["name"] for item in _inspector().get_indexes(table)}
    if name not in indexes:
        op.create_index(name, table, columns)


def upgrade() -> None:
    _add_unique("jobs", "uq_job_tenant_id", ["company_id", "id"])
    _add_unique("research_sources", "uq_research_source_tenant_group_id", ["company_id", "group_id", "id"])
    _add_column("research_sources", sa.Column("crawl_mode", sa.String(24), nullable=False, server_default="legacy"))
    _add_column("research_sources", sa.Column("crawl_page_limit", sa.Integer(), nullable=False, server_default="1000"))
    _add_column("research_sources", sa.Column("render_mode", sa.String(24), nullable=False, server_default="http_only"))
    _add_column("research_sources", sa.Column("resource_hosts_json", sa.JSON(), nullable=False, server_default="[]"))
    _add_column("research_sources", sa.Column("schedule_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    _create_table_if_missing(
        "web_crawl_runs",
        sa.Column("company_id", sa.String(36), nullable=False),
        sa.Column("group_id", sa.String(36), nullable=False),
        sa.Column("source_id", sa.String(36), nullable=False),
        sa.Column("cycle_id", sa.String(36), nullable=False),
        sa.Column("job_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="queued"),
        sa.Column("page_limit", sa.Integer(), nullable=False, server_default="1000"),
        sa.Column("counters_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("config_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("company_id", "source_id", "cycle_id", name="uq_web_crawl_run_cycle_source"),
        sa.UniqueConstraint("company_id", "id", name="uq_web_crawl_run_tenant_id"),
        sa.ForeignKeyConstraint(["company_id", "source_id"], ["research_sources.company_id", "research_sources.id"], name="fk_web_crawl_run_source_tenant", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id", "group_id", "source_id"], ["research_sources.company_id", "research_sources.group_id", "research_sources.id"], name="fk_web_crawl_run_source_group_tenant", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id", "job_id"], ["jobs.company_id", "jobs.id"], name="fk_web_crawl_run_job_tenant", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id", "group_id"], ["meta_page_groups.company_id", "meta_page_groups.id"], name="fk_web_crawl_run_group_tenant", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id", "cycle_id"], ["research_cycles.company_id", "research_cycles.id"], name="fk_web_crawl_run_cycle_tenant", ondelete="CASCADE"),
    )
    _create_index_if_missing("ix_web_crawl_run_status_updated", "web_crawl_runs", ["status", "updated_at"])

    _create_table_if_missing(
        "web_crawl_pages",
        sa.Column("company_id", sa.String(36), nullable=False),
        sa.Column("run_id", sa.String(36), nullable=False),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("depth", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(32), nullable=False, server_default="queued"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("http_status", sa.Integer()),
        sa.Column("etag", sa.String(500)),
        sa.Column("last_modified", sa.String(500)),
        sa.Column("error_json", sa.JSON()),
        sa.Column("evidence_id", sa.String(36)),
        sa.Column("observation_id", sa.String(36)),
        sa.Column("evidence_version_id", sa.String(36)),
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("company_id", "run_id", "url", name="uq_web_crawl_page_url"),
        sa.ForeignKeyConstraint(["company_id", "run_id"], ["web_crawl_runs.company_id", "web_crawl_runs.id"], name="fk_web_crawl_page_run_tenant", ondelete="CASCADE"),
    )
    _create_index_if_missing("ix_web_crawl_page_frontier", "web_crawl_pages", ["company_id", "run_id", "status", "depth"])

    _create_table_if_missing(
        "web_entities",
        sa.Column("company_id", sa.String(36), nullable=False),
        sa.Column("group_id", sa.String(36), nullable=False),
        sa.Column("source_id", sa.String(36), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("identity_key", sa.String(2048), nullable=False),
        sa.Column("title", sa.String(1000), nullable=False, server_default=""),
        sa.Column("canonical_url", sa.String(2048), nullable=False),
        sa.Column("latest_snapshot_id", sa.String(36)),
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("company_id", "source_id", "kind", "identity_key", name="uq_web_entity_identity"),
        sa.UniqueConstraint("company_id", "id", name="uq_web_entity_tenant_id"),
        sa.ForeignKeyConstraint(["company_id", "source_id"], ["research_sources.company_id", "research_sources.id"], name="fk_web_entity_source_tenant", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id", "group_id", "source_id"], ["research_sources.company_id", "research_sources.group_id", "research_sources.id"], name="fk_web_entity_source_group_tenant", ondelete="CASCADE"),
    )
    _create_index_if_missing("ix_web_entity_group_kind", "web_entities", ["company_id", "group_id", "kind", "title"])

    _create_table_if_missing(
        "web_entity_snapshots",
        sa.Column("company_id", sa.String(36), nullable=False),
        sa.Column("entity_id", sa.String(36), nullable=False),
        sa.Column("run_id", sa.String(36), nullable=False),
        sa.Column("evidence_id", sa.String(36), nullable=False),
        sa.Column("observation_id", sa.String(36), nullable=False),
        sa.Column("evidence_version_id", sa.String(36), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("parser_version", sa.String(80), nullable=False),
        sa.Column("data_json", sa.JSON(), nullable=False),
        sa.Column("id", sa.String(36), primary_key=True),
        sa.UniqueConstraint("company_id", "run_id", "entity_id", "content_hash", name="uq_web_entity_snapshot_run_hash"),
        sa.UniqueConstraint("company_id", "id", name="uq_web_entity_snapshot_tenant_id"),
        sa.ForeignKeyConstraint(["company_id", "entity_id"], ["web_entities.company_id", "web_entities.id"], name="fk_web_entity_snapshot_entity_tenant", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id", "run_id"], ["web_crawl_runs.company_id", "web_crawl_runs.id"], name="fk_web_entity_snapshot_run_tenant", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id", "evidence_id", "evidence_version_id"], ["market_evidence_versions.company_id", "market_evidence_versions.evidence_id", "market_evidence_versions.id"], name="fk_web_entity_snapshot_evidence_version"),
        sa.ForeignKeyConstraint(["company_id", "evidence_id", "observation_id", "evidence_version_id"], ["market_observations.company_id", "market_observations.evidence_id", "market_observations.id", "market_observations.evidence_version_id"], name="fk_web_entity_snapshot_observation_version"),
    )
    _create_index_if_missing("ix_web_entity_snapshot_history", "web_entity_snapshots", ["company_id", "entity_id", "observed_at"])

    _create_table_if_missing(
        "market_report_web_snapshots",
        sa.Column("company_id", sa.String(36), nullable=False),
        sa.Column("report_id", sa.String(36), nullable=False),
        sa.Column("snapshot_id", sa.String(36), nullable=False),
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("company_id", "report_id", "snapshot_id", name="uq_market_report_web_snapshot"),
        sa.ForeignKeyConstraint(["company_id", "report_id"], ["market_reports.company_id", "market_reports.id"], name="fk_market_report_web_snapshot_report_tenant", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id", "snapshot_id"], ["web_entity_snapshots.company_id", "web_entity_snapshots.id"], name="fk_market_report_web_snapshot_entity_tenant"),
    )
    _create_index_if_missing("ix_market_report_web_snapshot_report", "market_report_web_snapshots", ["company_id", "report_id"])

    _create_table_if_missing(
        "web_offer_snapshots",
        sa.Column("company_id", sa.String(36), nullable=False),
        sa.Column("entity_snapshot_id", sa.String(36), nullable=False),
        sa.Column("offer_key", sa.String(500), nullable=False),
        sa.Column("price_kind", sa.String(24), nullable=False),
        sa.Column("price", sa.Numeric(24, 6)),
        sa.Column("original_price", sa.Numeric(24, 6)),
        sa.Column("low_price", sa.Numeric(24, 6)),
        sa.Column("high_price", sa.Numeric(24, 6)),
        sa.Column("currency", sa.String(8)),
        sa.Column("availability", sa.String(120)),
        sa.Column("billing_unit", sa.String(80)),
        sa.Column("seller", sa.String(300)),
        sa.Column("offer_url", sa.String(2048), nullable=False),
        sa.Column("provenance_json", sa.JSON(), nullable=False),
        sa.Column("id", sa.String(36), primary_key=True),
        sa.ForeignKeyConstraint(["company_id", "entity_snapshot_id"], ["web_entity_snapshots.company_id", "web_entity_snapshots.id"], name="fk_web_offer_snapshot_entity_tenant", ondelete="CASCADE"),
        sa.UniqueConstraint("company_id", "entity_snapshot_id", "offer_key", name="uq_web_offer_snapshot_identity"),
    )
    _add_column("web_offer_snapshots", sa.Column("original_price", sa.Numeric(24, 6)))
    _create_index_if_missing("ix_web_offer_price", "web_offer_snapshots", ["company_id", "currency", "price"])


def downgrade() -> None:
    op.drop_index("ix_web_offer_price", table_name="web_offer_snapshots")
    op.drop_table("web_offer_snapshots")
    op.drop_index("ix_market_report_web_snapshot_report", table_name="market_report_web_snapshots")
    op.drop_table("market_report_web_snapshots")
    op.drop_index("ix_web_entity_snapshot_history", table_name="web_entity_snapshots")
    op.drop_table("web_entity_snapshots")
    op.drop_index("ix_web_entity_group_kind", table_name="web_entities")
    op.drop_table("web_entities")
    op.drop_index("ix_web_crawl_page_frontier", table_name="web_crawl_pages")
    op.drop_table("web_crawl_pages")
    op.drop_index("ix_web_crawl_run_status_updated", table_name="web_crawl_runs")
    op.drop_table("web_crawl_runs")
    op.drop_column("research_sources", "schedule_enabled")
    op.drop_column("research_sources", "resource_hosts_json")
    op.drop_column("research_sources", "render_mode")
    op.drop_column("research_sources", "crawl_page_limit")
    op.drop_column("research_sources", "crawl_mode")
    with op.batch_alter_table("research_sources") as batch:
        batch.drop_constraint("uq_research_source_tenant_group_id", type_="unique")
    with op.batch_alter_table("jobs") as batch:
        batch.drop_constraint("uq_job_tenant_id", type_="unique")
