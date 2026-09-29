"""Persist daily AI reservations and provider usage."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0022_ai_usage_budget"
down_revision = "0021_page_workspace_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "ai_usage_budget_days" not in tables:
        op.create_table(
            "ai_usage_budget_days",
            sa.Column("company_id", sa.String(36), sa.ForeignKey("companies.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("budget_date", sa.Date(), primary_key=True),
            sa.Column("limit_micro_usd", sa.Integer(), nullable=False),
            sa.Column("reserved_micro_usd", sa.Integer(), server_default="0", nullable=False),
            sa.Column("spent_micro_usd", sa.Integer(), server_default="0", nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint("limit_micro_usd >= 0", name="ck_ai_budget_day_limit_nonnegative"),
            sa.CheckConstraint("reserved_micro_usd >= 0", name="ck_ai_budget_day_reserved_nonnegative"),
            sa.CheckConstraint("spent_micro_usd >= 0", name="ck_ai_budget_day_spent_nonnegative"),
        )

    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "ai_usage_ledger" not in tables:
        op.create_table(
            "ai_usage_ledger",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("company_id", sa.String(36), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
            sa.Column("request_key", sa.String(220), nullable=False),
            sa.Column("provider", sa.String(32), nullable=False),
            sa.Column("model", sa.String(160), nullable=False),
            sa.Column("operation", sa.String(80), nullable=False),
            sa.Column("budget_class", sa.String(24), nullable=False),
            sa.Column("budget_date", sa.Date(), nullable=False),
            sa.Column("pricing_version", sa.String(100), nullable=False),
            sa.Column("cost_basis", sa.String(80), nullable=False),
            sa.Column("reserved_micro_usd", sa.Integer(), nullable=False),
            sa.Column("actual_micro_usd", sa.Integer(), nullable=True),
            sa.Column("input_tokens", sa.Integer(), nullable=True),
            sa.Column("output_tokens", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(24), nullable=False),
            sa.Column("result_json", sa.JSON(), nullable=True),
            sa.Column("unknown_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("error_code", sa.String(80), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("company_id", "request_key", name="uq_ai_usage_company_request"),
            sa.CheckConstraint("reserved_micro_usd >= 0", name="ck_ai_usage_reserved_nonnegative"),
            sa.CheckConstraint("actual_micro_usd IS NULL OR actual_micro_usd >= 0", name="ck_ai_usage_actual_nonnegative"),
            sa.CheckConstraint("input_tokens IS NULL OR input_tokens >= 0", name="ck_ai_usage_input_nonnegative"),
            sa.CheckConstraint("output_tokens IS NULL OR output_tokens >= 0", name="ck_ai_usage_output_nonnegative"),
        )
        op.create_index(
            "ix_ai_usage_company_date_status", "ai_usage_ledger", ["company_id", "budget_date", "status"]
        )


def downgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "ai_usage_ledger" in tables:
        op.drop_index("ix_ai_usage_company_date_status", table_name="ai_usage_ledger")
        op.drop_table("ai_usage_ledger")
    if "ai_usage_budget_days" in tables:
        op.drop_table("ai_usage_budget_days")
