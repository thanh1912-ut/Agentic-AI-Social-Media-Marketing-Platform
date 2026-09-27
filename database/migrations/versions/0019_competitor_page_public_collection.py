"""Add public competitor Page collection settings and shared crawl throttling."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0019_competitor_page_public_collection"
down_revision = "0018_mailguard_pilot_workflows"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "research_sources" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("research_sources")}
    additions = (
        ("collection_mode", sa.String(24), "'legacy'"),
        ("collection_post_limit", sa.Integer(), "50"),
        ("collection_status", sa.String(40), "'not_started'"),
        ("collection_last_method", sa.String(24), None),
        ("last_collection_attempt_at", sa.DateTime(timezone=True), None),
        ("last_collection_success_at", sa.DateTime(timezone=True), None),
    )
    for name, column_type, default in additions:
        if name not in columns:
            kwargs = {"nullable": name not in {"collection_mode", "collection_post_limit", "collection_status"}}
            if default is not None:
                kwargs["server_default"] = sa.text(default)
            op.add_column("research_sources", sa.Column(name, column_type, **kwargs))

    op.execute(sa.text(
        "UPDATE research_sources SET collection_mode = CASE "
        "WHEN source_type <> 'competitor_facebook_page' THEN 'legacy' "
        "WHEN status = 'active' THEN 'meta_api' ELSE 'manual' END "
        "WHERE collection_mode = 'legacy'"
    ))
    if not any(constraint.get("name") == "ck_research_source_collection_post_limit"
               for constraint in inspector.get_check_constraints("research_sources")):
        if op.get_bind().dialect.name == "sqlite":
            with op.batch_alter_table("research_sources") as batch_op:
                batch_op.create_check_constraint(
                    "ck_research_source_collection_post_limit",
                    "collection_post_limit BETWEEN 1 AND 100",
                )
        else:
            op.create_check_constraint(
                "ck_research_source_collection_post_limit", "research_sources",
                "collection_post_limit BETWEEN 1 AND 100",
            )
    if "crawl_host_throttles" not in inspector.get_table_names():
        op.create_table(
            "crawl_host_throttles",
            sa.Column("host", sa.String(255), primary_key=True),
            sa.Column("next_allowed_at", sa.DateTime(timezone=True), nullable=False),
        )
    op.execute(sa.text(
        "INSERT INTO crawl_host_throttles(host, next_allowed_at) "
        "VALUES ('facebook.com', CURRENT_TIMESTAMP) ON CONFLICT (host) DO NOTHING"
    ))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "crawl_host_throttles" in tables:
        op.drop_table("crawl_host_throttles")
    if "research_sources" not in tables:
        return
    columns = {column["name"] for column in inspector.get_columns("research_sources")}
    if "ck_research_source_collection_post_limit" in {
        constraint.get("name") for constraint in inspector.get_check_constraints("research_sources")
    }:
        if op.get_bind().dialect.name == "sqlite":
            with op.batch_alter_table("research_sources") as batch_op:
                batch_op.drop_constraint("ck_research_source_collection_post_limit", type_="check")
        else:
            op.drop_constraint("ck_research_source_collection_post_limit", "research_sources", type_="check")
    for name in (
        "last_collection_success_at", "last_collection_attempt_at", "collection_last_method",
        "collection_status", "collection_post_limit", "collection_mode",
    ):
        if name in columns:
            op.drop_column("research_sources", name)
