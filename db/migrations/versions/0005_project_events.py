"""Project events for SSE replay.

Revision ID: 0005
Revises: 0004
Create Date: 2025-01-01 00:00:05

"""
from typing import Sequence, Union
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE project_events ( id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
          event_type TEXT NOT NULL, sequence_no BIGINT NOT NULL,
          payload JSONB NOT NULL, job_id UUID, user_id UUID REFERENCES users(id),
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW() );
    """)
    op.execute("CREATE UNIQUE INDEX idx_project_events_seq ON project_events(project_id, sequence_no);")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS project_events;")

