"""Job runs table.

Revision ID: 0004
Revises: 0003
Create Date: 2025-01-01 00:00:04

"""
from typing import Sequence, Union
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE job_runs ( id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          job_id UUID NOT NULL UNIQUE, job_type TEXT NOT NULL,
          project_id UUID REFERENCES projects(id),
          input_contract_id UUID, input_schema TEXT, output_contract_id UUID, output_schema TEXT,
          status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','running','complete','failed','retrying')),
          worker_id TEXT, priority INT NOT NULL DEFAULT 5, retry_count INT NOT NULL DEFAULT 0, max_retries INT NOT NULL DEFAULT 3,
          queued_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), started_at TIMESTAMPTZ, completed_at TIMESTAMPTZ,
          duration_ms INT, error_code TEXT, error_message TEXT, error_traceback TEXT,
          input_snapshot JSONB, context JSONB NOT NULL DEFAULT '{}',
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW() );
    """)
    op.execute("CREATE INDEX idx_job_runs_project ON job_runs(project_id);")
    op.execute("CREATE INDEX idx_job_runs_queued_at ON job_runs(queued_at DESC);")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS job_runs;")

