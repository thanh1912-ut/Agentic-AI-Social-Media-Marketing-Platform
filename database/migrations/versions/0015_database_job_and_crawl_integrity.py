"""Fence stale workers and close tenant/provenance gaps in website crawl rows."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0015_database_job_and_crawl_integrity"
down_revision = "0014_website_catalog_intelligence"
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_column(table: str, column: str) -> bool:
    return column in {item["name"] for item in _inspector().get_columns(table)}


def _has_constraint(table: str, name: str) -> bool:
    inspector = _inspector()
    return any(item.get("name") == name for item in inspector.get_foreign_keys(table)) or any(
        item.get("name") == name for item in inspector.get_unique_constraints(table)
    ) or any(item.get("name") == name for item in inspector.get_check_constraints(table))


def _add_column(table: str, column: sa.Column) -> None:
    if not _has_column(table, column.name):
        op.add_column(table, column)


def _assert_no_rows(sql: str, description: str) -> None:
    count = op.get_bind().execute(sa.text(sql)).scalar_one()
    if count:
        raise RuntimeError(
            f"Migration 0015 stopped: found {count} {description}. "
            "Repair those rows explicitly and retry; this migration never rewrites history."
        )


def _add_fk(
    table: str,
    name: str,
    local: list[str],
    remote_table: str,
    remote: list[str],
    *,
    ondelete: str | None = None,
    deferrable: bool = False,
) -> None:
    if not _has_constraint(table, name):
        op.create_foreign_key(
            name, table, remote_table, local, remote,
            ondelete=ondelete, deferrable=deferrable,
            initially="DEFERRED" if deferrable else None,
        )


def upgrade() -> None:
    _add_column("jobs", sa.Column("claim_token", sa.String(36), nullable=True))
    _add_column("jobs", sa.Column("dispatch_attempts", sa.Integer(), nullable=False, server_default="0"))
    _add_column("jobs", sa.Column("last_dispatch_at", sa.DateTime(timezone=True), nullable=True))
    _add_column("jobs", sa.Column("last_dispatch_error", sa.String(80), nullable=True))

    if op.get_bind().dialect.name != "postgresql":
        # SQLite is retained for fast unit tests. PostgreSQL is the authoritative
        # dialect for the composite tenant constraints added below.
        return

    _assert_no_rows(
        "SELECT count(*) FROM web_crawl_runs r LEFT JOIN jobs j "
        "ON j.company_id=r.company_id AND j.id=r.job_id WHERE j.id IS NULL",
        "web crawl runs whose job belongs to a different workspace or is missing",
    )
    _assert_no_rows(
        "SELECT count(*) FROM web_crawl_pages p WHERE "
        "(p.evidence_id IS NULL OR p.observation_id IS NULL OR p.evidence_version_id IS NULL) "
        "AND NOT (p.evidence_id IS NULL AND p.observation_id IS NULL AND p.evidence_version_id IS NULL)",
        "web crawl pages with partial evidence references",
    )
    _assert_no_rows(
        "SELECT count(*) FROM web_crawl_pages p LEFT JOIN market_observations o "
        "ON o.company_id=p.company_id AND o.evidence_id=p.evidence_id "
        "AND o.id=p.observation_id AND o.evidence_version_id=p.evidence_version_id "
        "WHERE p.observation_id IS NOT NULL AND o.id IS NULL",
        "web crawl page references whose observation/version does not match",
    )
    _assert_no_rows(
        "SELECT count(*) FROM web_crawl_pages p LEFT JOIN market_evidence_versions v "
        "ON v.company_id=p.company_id AND v.evidence_id=p.evidence_id "
        "AND v.id=p.evidence_version_id "
        "WHERE p.evidence_version_id IS NOT NULL AND v.id IS NULL",
        "web crawl page references whose evidence version is missing",
    )
    _assert_no_rows(
        "SELECT count(*) FROM web_entities e LEFT JOIN web_entity_snapshots s "
        "ON s.company_id=e.company_id AND s.entity_id=e.id AND s.id=e.latest_snapshot_id "
        "WHERE e.latest_snapshot_id IS NOT NULL AND s.id IS NULL",
        "web entity latest-snapshot pointers that do not belong to that entity/workspace",
    )

    if not _has_constraint("web_entity_snapshots", "uq_web_entity_snapshot_entity_tenant_id"):
        op.create_unique_constraint(
            "uq_web_entity_snapshot_entity_tenant_id", "web_entity_snapshots",
            ["company_id", "entity_id", "id"],
        )
    _add_fk(
        "web_crawl_runs", "fk_web_crawl_run_job_tenant",
        ["company_id", "job_id"], "jobs", ["company_id", "id"], ondelete="CASCADE",
    )
    # The original model created by revision 0001 could leave this global
    # single-column edge behind because revision 0014 skipped existing tables.
    for foreign_key in _inspector().get_foreign_keys("web_crawl_runs"):
        if foreign_key.get("referred_table") == "jobs" and foreign_key.get("constrained_columns") == ["job_id"]:
            if foreign_key.get("name"):
                op.drop_constraint(foreign_key["name"], "web_crawl_runs", type_="foreignkey")
    _add_fk(
        "web_crawl_pages", "fk_web_crawl_page_evidence_version_tenant",
        ["company_id", "evidence_id", "evidence_version_id"], "market_evidence_versions",
        ["company_id", "evidence_id", "id"],
    )
    _add_fk(
        "web_crawl_pages", "fk_web_crawl_page_observation_version_tenant",
        ["company_id", "evidence_id", "observation_id", "evidence_version_id"],
        "market_observations", ["company_id", "evidence_id", "id", "evidence_version_id"],
    )
    if not _has_constraint("web_crawl_pages", "ck_web_crawl_page_evidence_refs_all_or_none"):
        op.create_check_constraint(
            "ck_web_crawl_page_evidence_refs_all_or_none", "web_crawl_pages",
            "(evidence_id IS NULL AND observation_id IS NULL AND evidence_version_id IS NULL) OR "
            "(evidence_id IS NOT NULL AND observation_id IS NOT NULL AND evidence_version_id IS NOT NULL)",
        )
    op.execute(sa.text("""
        CREATE OR REPLACE FUNCTION verify_web_entity_latest_snapshot()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_TABLE_NAME = 'web_entities' THEN
                IF NEW.latest_snapshot_id IS NOT NULL AND NOT EXISTS (
                    SELECT 1 FROM web_entity_snapshots s
                    WHERE s.company_id = NEW.company_id
                      AND s.entity_id = NEW.id
                      AND s.id = NEW.latest_snapshot_id
                ) THEN
                    RAISE EXCEPTION 'web entity latest snapshot must belong to the same entity and workspace'
                        USING ERRCODE = '23503';
                END IF;
                RETURN NEW;
            END IF;
            IF EXISTS (
                SELECT 1 FROM web_entities e
                WHERE e.company_id = OLD.company_id AND e.id = OLD.entity_id
                  AND e.latest_snapshot_id = OLD.id
            ) THEN
                RAISE EXCEPTION 'cannot delete or move a snapshot still marked latest'
                    USING ERRCODE = '23503';
            END IF;
            RETURN OLD;
        END;
        $$
    """))
    op.execute(sa.text("DROP TRIGGER IF EXISTS trg_web_entity_latest_snapshot_guard ON web_entities"))
    op.execute(sa.text("""
        CREATE CONSTRAINT TRIGGER trg_web_entity_latest_snapshot_guard
        AFTER INSERT OR UPDATE ON web_entities
        DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
        EXECUTE FUNCTION verify_web_entity_latest_snapshot()
    """))
    op.execute(sa.text("DROP TRIGGER IF EXISTS trg_web_entity_snapshot_delete_guard ON web_entity_snapshots"))
    op.execute(sa.text("""
        CREATE CONSTRAINT TRIGGER trg_web_entity_snapshot_delete_guard
        AFTER DELETE ON web_entity_snapshots
        DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
        EXECUTE FUNCTION verify_web_entity_latest_snapshot()
    """))


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for name, table in (
            ("ck_web_crawl_page_evidence_refs_all_or_none", "web_crawl_pages"),
            ("fk_web_crawl_page_observation_version_tenant", "web_crawl_pages"),
            ("fk_web_crawl_page_evidence_version_tenant", "web_crawl_pages"),
            ("fk_web_crawl_run_job_tenant", "web_crawl_runs"),
        ):
            if _has_constraint(table, name):
                op.drop_constraint(name, table, type_="check" if name.startswith("ck_") else "foreignkey")
        if _has_constraint("web_entity_snapshots", "uq_web_entity_snapshot_entity_tenant_id"):
            op.drop_constraint("uq_web_entity_snapshot_entity_tenant_id", "web_entity_snapshots", type_="unique")
        op.execute(sa.text("DROP TRIGGER IF EXISTS trg_web_entity_latest_snapshot_guard ON web_entities"))
        op.execute(sa.text("DROP TRIGGER IF EXISTS trg_web_entity_snapshot_delete_guard ON web_entity_snapshots"))
        op.execute(sa.text("DROP FUNCTION IF EXISTS verify_web_entity_latest_snapshot()"))
    for name in ("last_dispatch_error", "last_dispatch_at", "dispatch_attempts", "claim_token"):
        if _has_column("jobs", name):
            op.drop_column("jobs", name)
