"""Geometry rule sets (StyleProfile → GeometryRuleSet).

Revision ID: 0007
Revises: 0006
Create Date: 2025-01-01 00:00:07

"""
from typing import Sequence, Union
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE geometry_rule_sets ( id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          style_profile_id UUID NOT NULL REFERENCES style_profiles(id),
          derived_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          confidence_overall FLOAT NOT NULL, rules JSONB NOT NULL DEFAULT '[]',
          schema_version TEXT NOT NULL DEFAULT '1.0', created_at TIMESTAMPTZ NOT NULL DEFAULT NOW() );
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS geometry_rule_sets;")

