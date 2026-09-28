"""Re-evaluate active competitor Pages with the Tier 0 collector."""

from alembic import op
import sqlalchemy as sa


revision = "0020_facebook_cli_public_collector"
down_revision = "0019_competitor_page_public_collection"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Only schedules that users already enabled are re-evaluated. Historical
    # WebCrawlRun rows remain untouched and disabled sources stay disabled.
    op.execute(sa.text(
        "UPDATE research_sources "
        "SET collection_status = 'not_started', status = 'active', error_json = NULL, "
        "next_due_at = CURRENT_TIMESTAMP "
        "WHERE source_type = 'competitor_facebook_page' AND active = TRUE "
        "AND collection_mode = 'public_web' AND schedule_enabled = TRUE "
        "AND collection_status IN ('blocked_robots', 'platform_permission_required')"
    ))
    op.execute(sa.text(
        "UPDATE meta_page_groups SET next_due_at = ("
        " SELECT MIN(rs.next_due_at) FROM research_sources AS rs "
        " WHERE rs.company_id = meta_page_groups.company_id "
        " AND rs.group_id = meta_page_groups.id AND rs.active = TRUE "
        " AND rs.schedule_enabled = TRUE AND rs.next_due_at IS NOT NULL"
        ") WHERE id IN ("
        " SELECT group_id FROM research_sources "
        " WHERE source_type = 'competitor_facebook_page' AND active = TRUE "
        " AND collection_mode = 'public_web' AND schedule_enabled = TRUE "
        " AND collection_status = 'not_started'"
        ")"
    ))


def downgrade() -> None:
    # Runtime outcomes and historical runs cannot safely be reconstructed into
    # the former permission-gate status, so this data-only migration is kept.
    pass
