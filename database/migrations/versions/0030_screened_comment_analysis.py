"""Immutable screened comment batches and Gemini analysis provenance.

DDL is frozen here; upgrade does not import current application metadata.
"""
from alembic import op
import sqlalchemy as sa

revision = "0030_screened_comment_analysis"
down_revision = "0029_comment_suppression"
branch_labels = None
depends_on = None

TABLE_DDL = [
    (
        "research_comment_analysis_batches",
        """CREATE TABLE research_comment_analysis_batches (
    company_id VARCHAR(36) NOT NULL,
    source_id VARCHAR(36) NOT NULL,
    decision_id VARCHAR(36) NOT NULL,
    policy_revision_id VARCHAR(36) NOT NULL,
    request_key VARCHAR(36) NOT NULL,
    input_hash VARCHAR(64) NOT NULL,
    assessment_reference TEXT NOT NULL,
    assessed_by VARCHAR(36) NOT NULL,
    provider VARCHAR(24) DEFAULT 'gemini' NOT NULL,
    model VARCHAR(80) DEFAULT 'gemini-3.8-flash' NOT NULL,
    status VARCHAR(24) DEFAULT 'queued' NOT NULL,
    result_json JSON,
    error_code VARCHAR(80),
    coverage_json JSON NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    completed_at TIMESTAMP WITH TIME ZONE,
    provider_valid_until TIMESTAMP WITH TIME ZONE NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    id VARCHAR(36) NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_comment_analysis_tenant_source_id UNIQUE (company_id, source_id, id),
    CONSTRAINT uq_comment_analysis_request UNIQUE (company_id, source_id, request_key),
    CONSTRAINT fk_comment_analysis_decision FOREIGN KEY(company_id, source_id, decision_id) REFERENCES research_comment_processing_decisions (company_id, source_id, id) ON DELETE CASCADE,
    CONSTRAINT fk_comment_analysis_policy FOREIGN KEY(company_id, source_id, policy_revision_id) REFERENCES research_privacy_policy_revisions (company_id, source_id, id) ON DELETE CASCADE,
    CONSTRAINT ck_comment_analysis_status CHECK (status IN ('queued','running','completed','deferred_budget','failed','expired','suppressed')),
    CONSTRAINT ck_comment_analysis_provider CHECK (provider = 'gemini' AND model = 'gemini-3.8-flash'),
    CONSTRAINT ck_comment_analysis_expiry CHECK (provider_valid_until > created_at AND expires_at > created_at),
    CONSTRAINT ck_comment_analysis_max_age CHECK (expires_at <= created_at + INTERVAL '90 days'),
    FOREIGN KEY(assessed_by) REFERENCES users (id)
)
""",
        ['CREATE INDEX ix_comment_analysis_expiry ON research_comment_analysis_batches (expires_at, status)', 'CREATE INDEX ix_comment_analysis_source_created ON research_comment_analysis_batches (company_id, source_id, created_at)'],
    ),
    (
        "research_screened_comments",
        """CREATE TABLE research_screened_comments (
    company_id VARCHAR(36) NOT NULL,
    source_id VARCHAR(36) NOT NULL,
    batch_id VARCHAR(36) NOT NULL,
    version_id VARCHAR(36) NOT NULL,
    excerpt_ciphertext TEXT,
    excerpt_hash VARCHAR(64) NOT NULL,
    source_content_hash VARCHAR(64) NOT NULL,
    content_edited BOOLEAN NOT NULL,
    id VARCHAR(36) NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_screened_comment_batch_version UNIQUE (company_id, batch_id, version_id),
    CONSTRAINT fk_screened_comment_batch FOREIGN KEY(company_id, source_id, batch_id) REFERENCES research_comment_analysis_batches (company_id, source_id, id) ON DELETE CASCADE,
    CONSTRAINT fk_screened_comment_version FOREIGN KEY(company_id, source_id, version_id) REFERENCES research_comment_versions (company_id, source_id, id) ON DELETE CASCADE
)
""",
        [],
    ),
]


def upgrade():
    inspector = sa.inspect(op.get_bind())
    constraints = {item["name"] for item in inspector.get_unique_constraints("research_comment_versions")}
    if "uq_comment_version_tenant_source_id" not in constraints:
        op.create_unique_constraint("uq_comment_version_tenant_source_id", "research_comment_versions", ["company_id", "source_id", "id"])
    tables = set(inspector.get_table_names())
    for name, statement, indexes in TABLE_DDL:
        if name not in tables:
            op.execute(sa.text(statement))
            for index in indexes:
                op.execute(sa.text(index))


def downgrade():
    raise RuntimeError("Screened comment migration is forward-only; disable analysis without deleting privacy history")
