"""Annotation sessions for human correction loop.

Revision ID: 0006
Revises: 0005
Create Date: 2025-01-01 00:00:06

"""
from typing import Sequence, Union
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE annotation_sessions ( id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          project_id UUID NOT NULL REFERENCES projects(id),
          parsed_plan_id UUID NOT NULL REFERENCES parsed_plans(id),
          user_id UUID NOT NULL REFERENCES users(id),
          status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','submitted','applying','applied','rejected')),
          trigger TEXT NOT NULL CHECK (trigger IN ('ambiguity_flag','user_initiated','critique_failure')),
          edits JSONB NOT NULL DEFAULT '[]', submitted_at TIMESTAMPTZ, applied_at TIMESTAMPTZ,
          downstream_recomputed BOOLEAN NOT NULL DEFAULT FALSE, export_to_training BOOLEAN NOT NULL DEFAULT FALSE,
          schema_version TEXT NOT NULL DEFAULT '1.0',
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW() );
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS annotation_sessions;")

