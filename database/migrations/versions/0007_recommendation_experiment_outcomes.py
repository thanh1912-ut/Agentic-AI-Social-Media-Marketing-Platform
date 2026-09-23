"""Store evidence-backed outcomes for accepted recommendation experiments."""

from alembic import op
import sqlalchemy as sa


revision = "0007_recommendation_experiment_outcomes"
down_revision = "0006_recommendation_feedback_and_brief_drafts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "recommendation_experiment_outcomes" not in inspector.get_table_names():
        op.create_table(
            "recommendation_experiment_outcomes",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("company_id", sa.String(length=36), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
            sa.Column("campaign_id", sa.String(length=36), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False),
            sa.Column("draft_id", sa.String(length=36), sa.ForeignKey("campaign_brief_revision_drafts.id", ondelete="CASCADE"), nullable=False),
            sa.Column("source_id", sa.String(length=160), nullable=False),
            sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
            sa.Column("metric", sa.String(length=80), nullable=False),
            sa.Column("min_post_age_hours", sa.Integer(), nullable=False),
            sa.Column("max_post_age_hours", sa.Integer(), nullable=False),
            sa.Column("baseline_window_from", sa.DateTime(timezone=True), nullable=False),
            sa.Column("baseline_window_to", sa.DateTime(timezone=True), nullable=False),
            sa.Column("followup_window_from", sa.DateTime(timezone=True), nullable=False),
            sa.Column("followup_window_to", sa.DateTime(timezone=True), nullable=False),
            sa.Column("baseline_value", sa.Numeric(18, 8), nullable=False),
            sa.Column("followup_value", sa.Numeric(18, 8), nullable=False),
            sa.Column("absolute_change", sa.Numeric(18, 8), nullable=False),
            sa.Column("relative_change", sa.Numeric(18, 8)),
            sa.Column("baseline_sample_size", sa.Integer(), nullable=False),
            sa.Column("followup_sample_size", sa.Integer(), nullable=False),
            sa.Column("baseline_coverage", sa.Numeric(8, 7), nullable=False),
            sa.Column("followup_coverage", sa.Numeric(8, 7), nullable=False),
            sa.Column("baseline_evidence_json", sa.JSON(), nullable=False),
            sa.Column("followup_evidence_json", sa.JSON(), nullable=False),
            sa.Column("limitations_json", sa.JSON(), nullable=False),
            sa.Column("recorded_by", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("draft_id", "request_fingerprint", name="uq_experiment_outcome_request"),
        )
    indexes = {item["name"] for item in sa.inspect(op.get_bind()).get_indexes("recommendation_experiment_outcomes")}
    if "ix_experiment_outcome_company_draft" not in indexes:
        op.create_index(
            "ix_experiment_outcome_company_draft",
            "recommendation_experiment_outcomes",
            ["company_id", "draft_id", "created_at"],
        )


def downgrade() -> None:
    indexes = {item["name"] for item in sa.inspect(op.get_bind()).get_indexes("recommendation_experiment_outcomes")}
    if "ix_experiment_outcome_company_draft" in indexes:
        op.drop_index("ix_experiment_outcome_company_draft", table_name="recommendation_experiment_outcomes")
    if "recommendation_experiment_outcomes" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("recommendation_experiment_outcomes")
