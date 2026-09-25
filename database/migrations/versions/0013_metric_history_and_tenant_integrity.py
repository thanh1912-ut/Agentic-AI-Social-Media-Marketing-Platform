"""Preserve research/Meta history and enforce tenant-scoped relations."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0013_metric_history_and_tenant_integrity"
down_revision = "0012_market_research_and_page_groups"
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def _table_exists(name: str) -> bool:
    return name in _inspector().get_table_names()


def _column_exists(table: str, name: str) -> bool:
    return _table_exists(table) and name in {c["name"] for c in _inspector().get_columns(table)}


def _has_unique(table: str, name: str) -> bool:
    if not _table_exists(table):
        return False
    return name in {c.get("name") for c in _inspector().get_unique_constraints(table)}


def _has_foreign_key(table: str, name: str) -> bool:
    if not _table_exists(table):
        return False
    return name in {c.get("name") for c in _inspector().get_foreign_keys(table)}


def _add_column(table: str, column: sa.Column) -> None:
    if not _column_exists(table, column.name):
        if op.get_bind().dialect.name == "sqlite":
            with op.batch_alter_table(table) as batch:
                batch.add_column(column)
        else:
            op.add_column(table, column)


def _drop_column(table: str, name: str) -> None:
    if _column_exists(table, name):
        if op.get_bind().dialect.name == "sqlite":
            with op.batch_alter_table(table) as batch:
                batch.drop_column(name)
        else:
            op.drop_column(table, name)


def _add_unique(table: str, name: str, columns: list[str]) -> None:
    if not _has_unique(table, name):
        with op.batch_alter_table(table) as batch:
            batch.create_unique_constraint(name, columns)


def _add_fk(table: str, name: str, columns: list[str], target: str, target_columns: list[str], ondelete: str | None = None) -> None:
    if not _has_foreign_key(table, name):
        with op.batch_alter_table(table) as batch:
            batch.create_foreign_key(name, target, columns, target_columns, ondelete=ondelete)


def _drop_fk(table: str, name: str) -> None:
    if _has_foreign_key(table, name):
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(name, type_="foreignkey")


def _create_table(name: str, *columns, **kwargs) -> None:
    if not _table_exists(name):
        op.create_table(name, *columns, **kwargs)


def _assert_no_cross_tenant_links() -> None:
    checks = {
        "campaign group": "SELECT count(*) FROM campaigns c JOIN meta_page_groups g ON g.id=c.group_id WHERE c.group_id IS NOT NULL AND c.company_id<>g.company_id",
        "Page connection group": "SELECT count(*) FROM meta_page_connections p JOIN meta_page_groups g ON g.id=p.group_id WHERE p.company_id<>g.company_id",
        "research source group": "SELECT count(*) FROM research_sources s JOIN meta_page_groups g ON g.id=s.group_id WHERE s.company_id<>g.company_id",
        "research source Page": "SELECT count(*) FROM research_sources s JOIN meta_page_connections p ON p.id=s.connection_id WHERE s.connection_id IS NOT NULL AND s.company_id<>p.company_id",
        "campaign target Page": "SELECT count(*) FROM campaign_posts c JOIN meta_page_connections p ON p.id=c.target_connection_id WHERE c.target_connection_id IS NOT NULL AND c.company_id<>p.company_id",
        "evidence group": "SELECT count(*) FROM market_evidence e JOIN meta_page_groups g ON g.id=e.group_id WHERE e.company_id<>g.company_id",
        "evidence source": "SELECT count(*) FROM market_evidence e JOIN research_sources s ON s.id=e.source_id WHERE e.company_id<>s.company_id OR e.group_id<>s.group_id",
        "research cycle group": "SELECT count(*) FROM research_cycles c JOIN meta_page_groups g ON g.id=c.group_id WHERE c.company_id<>g.company_id",
        "report group": "SELECT count(*) FROM market_reports r JOIN meta_page_groups g ON g.id=r.group_id WHERE r.company_id<>g.company_id",
        "report cycle": "SELECT count(*) FROM market_reports r JOIN research_cycles c ON c.id=r.cycle_id WHERE r.cycle_id IS NOT NULL AND (r.company_id<>c.company_id OR r.group_id<>c.group_id)",
        "market observation evidence": "SELECT count(*) FROM market_observations o JOIN market_evidence e ON e.id=o.evidence_id WHERE o.company_id<>e.company_id",
        "campaign post": "SELECT count(*) FROM campaign_posts p JOIN campaigns c ON c.id=p.campaign_id WHERE p.company_id<>c.company_id",
        "post version": "SELECT count(*) FROM post_versions v JOIN campaign_posts p ON p.id=v.post_id WHERE v.company_id<>p.company_id OR v.campaign_id<>p.campaign_id",
        "post approval": "SELECT count(*) FROM post_approvals a JOIN campaign_posts p ON p.id=a.post_id LEFT JOIN post_versions v ON v.post_id=a.post_id AND v.version=a.version WHERE a.company_id<>p.company_id OR v.id IS NULL OR v.company_id<>a.company_id",
        "Meta publication": "SELECT count(*) FROM meta_publications m JOIN campaign_posts p ON p.id=m.post_id LEFT JOIN post_versions v ON v.post_id=m.post_id AND v.version=m.post_version WHERE m.company_id<>p.company_id OR v.id IS NULL OR v.company_id<>m.company_id",
    }
    violations = {
        label: int(op.get_bind().execute(sa.text(query)).scalar_one())
        for label, query in checks.items()
        if int(op.get_bind().execute(sa.text(query)).scalar_one())
    }
    if violations:
        details = ", ".join(f"{name}: {count}" for name, count in violations.items())
        raise RuntimeError("Migration 0013 stopped; fix cross-workspace references first (" + details + ").")
    multiple_reports = int(op.get_bind().execute(sa.text(
        "SELECT count(*) FROM (SELECT cycle_id FROM market_reports WHERE cycle_id IS NOT NULL "
        "GROUP BY cycle_id HAVING count(*) > 1) duplicates"
    )).scalar_one())
    if multiple_reports:
        raise RuntimeError("Migration 0013 stopped; a research cycle has multiple reports. Resolve those duplicates before upgrading.")
    if _column_exists("research_cycles", "report_id"):
        duplicate_reverse_links = int(op.get_bind().execute(sa.text(
            "SELECT count(*) FROM (SELECT report_id FROM research_cycles WHERE report_id IS NOT NULL "
            "GROUP BY report_id HAVING count(*) > 1) duplicates"
        )).scalar_one())
        if duplicate_reverse_links:
            raise RuntimeError("Migration 0013 stopped; a report is linked from multiple research cycles. Resolve those links before upgrading.")
        conflicting_report_links = int(op.get_bind().execute(sa.text(
            "SELECT count(*) FROM research_cycles c JOIN market_reports r ON r.id=c.report_id "
            "WHERE c.report_id IS NOT NULL AND r.cycle_id IS NOT NULL AND r.cycle_id<>c.id"
        )).scalar_one())
        if conflicting_report_links:
            raise RuntimeError("Migration 0013 stopped; a cycle/report reverse link conflicts with market_reports.cycle_id.")


def upgrade() -> None:
    bind = op.get_bind()
    _assert_no_cross_tenant_links()

    # Drop the old unconstrained reverse pointer after migrating its data to the
    # authoritative market_reports.cycle_id relationship.
    if _column_exists("research_cycles", "report_id"):
        for row in bind.execute(sa.text(
            "SELECT id, report_id FROM research_cycles WHERE report_id IS NOT NULL"
        )).mappings():
            bind.execute(sa.text(
                "UPDATE market_reports SET cycle_id=:cycle_id WHERE id=:report_id AND cycle_id IS NULL"
            ), {"cycle_id": row["id"], "report_id": row["report_id"]})

    _add_column("market_observations", sa.Column("evidence_version_id", sa.String(36), nullable=True))
    _create_table(
        "market_evidence_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("company_id", sa.String(36), nullable=False),
        sa.Column("evidence_id", sa.String(36), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("parser_version", sa.String(80), nullable=False),
        sa.Column("title", sa.String(1000), nullable=False, server_default=""),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("company_id", "evidence_id", "content_hash", "parser_version", name="uq_market_evidence_version_fingerprint"),
        sa.UniqueConstraint("company_id", "evidence_id", "id", name="uq_market_evidence_version_tenant_id"),
    )
    _create_table(
        "market_report_evidence",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("company_id", sa.String(36), nullable=False),
        sa.Column("group_id", sa.String(36), nullable=False),
        sa.Column("report_id", sa.String(36), nullable=False),
        sa.Column("observation_id", sa.String(36), nullable=False),
        sa.Column("evidence_id", sa.String(36), nullable=False),
        sa.Column("evidence_version_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("report_id", "observation_id", name="uq_market_report_evidence_observation"),
    )
    _create_table(
        "meta_post_metric_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("company_id", sa.String(36), nullable=False),
        sa.Column("meta_page_post_id", sa.String(36), nullable=False),
        sa.Column("snapshot_key", sa.String(200), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(40), nullable=False, server_default="meta_graph"),
        sa.Column("metric_definition", sa.String(100), nullable=False, server_default="meta_post_v1"),
        sa.Column("window_start", sa.DateTime(timezone=True)),
        sa.Column("window_end", sa.DateTime(timezone=True)),
        sa.Column("views", sa.Integer()),
        sa.Column("reactions", sa.Integer()),
        sa.Column("comments", sa.Integer()),
        sa.Column("shares", sa.Integer()),
        sa.Column("missing_metrics_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.UniqueConstraint("company_id", "meta_page_post_id", "snapshot_key", name="uq_meta_post_metric_snapshot_key"),
    )
    _create_table(
        "meta_page_metric_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("company_id", sa.String(36), nullable=False),
        sa.Column("connection_id", sa.String(36), nullable=False),
        sa.Column("page_id", sa.String(100), nullable=False),
        sa.Column("snapshot_key", sa.String(200), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(40), nullable=False, server_default="meta_graph"),
        sa.Column("metric_definition", sa.String(100), nullable=False, server_default="page_followers_v1"),
        sa.Column("window_start", sa.DateTime(timezone=True)),
        sa.Column("window_end", sa.DateTime(timezone=True)),
        sa.Column("followers", sa.Integer()),
        sa.Column("missing_metrics_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.UniqueConstraint("company_id", "connection_id", "snapshot_key", name="uq_meta_page_metric_snapshot_key"),
    )
    _create_table(
        "research_source_metric_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("company_id", sa.String(36), nullable=False),
        sa.Column("source_id", sa.String(36), nullable=False),
        sa.Column("snapshot_key", sa.String(200), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(40), nullable=False),
        sa.Column("metric_definition", sa.String(100), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True)),
        sa.Column("window_end", sa.DateTime(timezone=True)),
        sa.Column("followers", sa.Integer()),
        sa.Column("members", sa.Integer()),
        sa.Column("missing_metrics_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.UniqueConstraint("company_id", "source_id", "snapshot_key", name="uq_research_source_metric_snapshot_key"),
    )

    # Composite candidate keys make tenant identity part of every critical edge.
    unique_specs = [
        ("campaigns", "uq_campaign_tenant_id", ["company_id", "id"]),
        ("campaign_posts", "uq_campaign_post_tenant_id", ["company_id", "id"]),
        ("campaign_posts", "uq_campaign_post_tenant_campaign", ["company_id", "campaign_id", "id"]),
        ("post_versions", "uq_post_version_tenant_number", ["company_id", "post_id", "version"]),
        ("meta_page_groups", "uq_meta_page_group_tenant_id", ["company_id", "id"]),
        ("meta_page_connections", "uq_meta_connection_tenant_id", ["company_id", "id"]),
        ("meta_page_connections", "uq_meta_connection_tenant_page", ["company_id", "id", "page_id"]),
        ("research_sources", "uq_research_source_tenant_id", ["company_id", "id"]),
        ("research_cycles", "uq_research_cycle_tenant_id", ["company_id", "id"]),
        ("research_cycles", "uq_research_cycle_tenant_group_id", ["company_id", "group_id", "id"]),
        ("market_evidence", "uq_market_evidence_tenant_id", ["company_id", "id"]),
        ("market_evidence", "uq_market_evidence_tenant_group_id", ["company_id", "group_id", "id"]),
        ("market_observations", "uq_market_observation_tenant_evidence", ["company_id", "evidence_id", "id"]),
        ("market_observations", "uq_market_observation_tenant_version", ["company_id", "evidence_id", "id", "evidence_version_id"]),
        ("market_reports", "uq_market_report_tenant_id", ["company_id", "id"]),
        ("market_reports", "uq_market_report_tenant_group_id", ["company_id", "group_id", "id"]),
        ("market_reports", "uq_market_report_cycle", ["cycle_id"]),
        ("meta_page_posts", "uq_meta_page_post_tenant_id", ["company_id", "id"]),
    ]
    for table, name, columns in unique_specs:
        _add_unique(table, name, columns)

    # A report has one authoritative cycle reference after this migration.
    if _column_exists("research_cycles", "report_id"):
        if bind.dialect.name == "sqlite":
            with op.batch_alter_table("research_cycles") as batch:
                batch.drop_column("report_id")
        else:
            op.drop_column("research_cycles", "report_id")

    fk_specs = [
        ("campaigns", "fk_campaign_group_tenant", ["company_id", "group_id"], "meta_page_groups", ["company_id", "id"], None),
        ("campaign_posts", "fk_campaign_post_campaign_tenant", ["company_id", "campaign_id"], "campaigns", ["company_id", "id"], "CASCADE"),
        ("campaign_posts", "fk_campaign_post_target_tenant", ["company_id", "target_connection_id"], "meta_page_connections", ["company_id", "id"], None),
        ("post_versions", "fk_post_version_post_tenant", ["company_id", "campaign_id", "post_id"], "campaign_posts", ["company_id", "campaign_id", "id"], "CASCADE"),
        ("post_approvals", "fk_post_approval_version_tenant", ["company_id", "post_id", "version"], "post_versions", ["company_id", "post_id", "version"], "CASCADE"),
        ("meta_publications", "fk_meta_publication_version_tenant", ["company_id", "post_id", "post_version"], "post_versions", ["company_id", "post_id", "version"], "CASCADE"),
        ("meta_page_connections", "fk_meta_connection_group_tenant", ["company_id", "group_id"], "meta_page_groups", ["company_id", "id"], "CASCADE"),
        ("research_sources", "fk_research_source_group_tenant", ["company_id", "group_id"], "meta_page_groups", ["company_id", "id"], "CASCADE"),
        ("research_sources", "fk_research_source_connection_tenant", ["company_id", "connection_id"], "meta_page_connections", ["company_id", "id"], None),
        ("research_cycles", "fk_research_cycle_group_tenant", ["company_id", "group_id"], "meta_page_groups", ["company_id", "id"], "CASCADE"),
        ("market_evidence", "fk_market_evidence_group_tenant", ["company_id", "group_id"], "meta_page_groups", ["company_id", "id"], "CASCADE"),
        ("market_evidence", "fk_market_evidence_source_tenant", ["company_id", "source_id"], "research_sources", ["company_id", "id"], "CASCADE"),
        ("market_observations", "fk_market_observation_evidence_tenant", ["company_id", "evidence_id"], "market_evidence", ["company_id", "id"], "CASCADE"),
        ("market_evidence_versions", "fk_market_evidence_version_evidence_tenant", ["company_id", "evidence_id"], "market_evidence", ["company_id", "id"], "CASCADE"),
        ("market_observations", "fk_market_observation_version_tenant", ["company_id", "evidence_id", "evidence_version_id"], "market_evidence_versions", ["company_id", "evidence_id", "id"], None),
        ("market_reports", "fk_market_report_group_tenant", ["company_id", "group_id"], "meta_page_groups", ["company_id", "id"], "CASCADE"),
        ("market_reports", "fk_market_report_cycle_tenant", ["company_id", "group_id", "cycle_id"], "research_cycles", ["company_id", "group_id", "id"], None),
        ("market_report_evidence", "fk_market_report_evidence_report_tenant", ["company_id", "group_id", "report_id"], "market_reports", ["company_id", "group_id", "id"], "CASCADE"),
        ("market_report_evidence", "fk_market_report_evidence_group_tenant", ["company_id", "group_id", "evidence_id"], "market_evidence", ["company_id", "group_id", "id"], "CASCADE"),
        ("market_report_evidence", "fk_market_report_evidence_observation_version", ["company_id", "evidence_id", "observation_id", "evidence_version_id"], "market_observations", ["company_id", "evidence_id", "id", "evidence_version_id"], "CASCADE"),
        ("market_report_evidence", "fk_market_report_evidence_version_tenant", ["company_id", "evidence_id", "evidence_version_id"], "market_evidence_versions", ["company_id", "evidence_id", "id"], "CASCADE"),
        ("meta_post_metric_snapshots", "fk_meta_post_metric_post_tenant", ["company_id", "meta_page_post_id"], "meta_page_posts", ["company_id", "id"], "CASCADE"),
        ("meta_page_metric_snapshots", "fk_meta_page_metric_connection_tenant", ["company_id", "connection_id", "page_id"], "meta_page_connections", ["company_id", "id", "page_id"], "CASCADE"),
        ("research_source_metric_snapshots", "fk_research_source_metric_source_tenant", ["company_id", "source_id"], "research_sources", ["company_id", "id"], "CASCADE"),
    ]
    for table, name, columns, target, target_columns, ondelete in fk_specs:
        _add_fk(table, name, columns, target, target_columns, ondelete)

    _add_index("ix_market_evidence_version_evidence_captured", "market_evidence_versions", ["company_id", "evidence_id", "captured_at"])
    _add_index("ix_market_report_evidence_report", "market_report_evidence", ["company_id", "report_id"])
    _add_index("ix_meta_post_metric_history", "meta_post_metric_snapshots", ["company_id", "meta_page_post_id", "observed_at"])
    _add_index("ix_meta_page_metric_history", "meta_page_metric_snapshots", ["company_id", "page_id", "observed_at"])
    _add_index("ix_research_source_metric_history", "research_source_metric_snapshots", ["company_id", "source_id", "observed_at"])


def _add_index(name: str, table: str, columns: list[str]) -> None:
    indexes = {item["name"] for item in _inspector().get_indexes(table)}
    if name not in indexes:
        op.create_index(name, table, columns)


def downgrade() -> None:
    bind = op.get_bind()
    _add_column("research_cycles", sa.Column("report_id", sa.String(36), nullable=True))
    for row in bind.execute(sa.text("SELECT id, cycle_id FROM market_reports WHERE cycle_id IS NOT NULL")).mappings():
        bind.execute(sa.text(
            "UPDATE research_cycles SET report_id=:report_id WHERE id=:cycle_id"
        ), {"report_id": row["id"], "cycle_id": row["cycle_id"]})

    for table in ("research_source_metric_snapshots", "meta_page_metric_snapshots", "meta_post_metric_snapshots", "market_report_evidence"):
        if _table_exists(table):
            op.drop_table(table)
    _drop_fk("market_observations", "fk_market_observation_version_tenant")
    if _table_exists("market_evidence_versions"):
        op.drop_table("market_evidence_versions")
    _drop_column("market_observations", "evidence_version_id")

    # Tenant FKs and candidate keys are intentionally retained during downgrade:
    # dropping them would weaken the existing data-integrity guarantees.
