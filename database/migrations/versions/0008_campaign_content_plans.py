"""Store editable strategy and content slots on each campaign."""

from alembic import op
import sqlalchemy as sa


revision = "0008_campaign_content_plans"
down_revision = "0007_recommendation_experiment_outcomes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("campaigns")}
    if "content_plan_json" not in columns:
        op.add_column(
            "campaigns",
            sa.Column(
                "content_plan_json",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'"),
            ),
        )


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("campaigns")}
    if "content_plan_json" in columns:
        op.drop_column("campaigns", "content_plan_json")
