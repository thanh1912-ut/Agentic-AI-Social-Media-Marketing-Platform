"""Create the tenant, auth, document and durable job ledger."""

from alembic import op
from sqlalchemy import inspect

from database.models import Base


revision = "0001_backend_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    for table in reversed(Base.metadata.sorted_tables):
        if table.name in inspector.get_table_names():
            table.drop(bind=bind, checkfirst=True)

