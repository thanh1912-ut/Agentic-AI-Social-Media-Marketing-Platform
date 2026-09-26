"""Guard updates and deletes of a web entity's latest snapshot."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0017_web_entity_snapshot_immutability"
down_revision = "0016_market_report_evidence_created_at"
branch_labels = None
depends_on = None


def _set_snapshot_guard(events: str) -> None:
    op.execute(sa.text(
        "DROP TRIGGER IF EXISTS trg_web_entity_snapshot_delete_guard ON web_entity_snapshots"
    ))
    op.execute(sa.text(f"""
        CREATE CONSTRAINT TRIGGER trg_web_entity_snapshot_delete_guard
        AFTER {events} ON web_entity_snapshots
        DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
        EXECUTE FUNCTION verify_web_entity_latest_snapshot()
    """))


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        _set_snapshot_guard("UPDATE OR DELETE")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        _set_snapshot_guard("DELETE")
