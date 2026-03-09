"""Users + FK fix for projects.owner_id.

Revision ID: 0002
Revises: 0001
Create Date: 2025-01-01 00:00:02

"""
from typing import Sequence, Union
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE users (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          email TEXT NOT NULL UNIQUE, display_name TEXT NOT NULL, avatar_url TEXT,
          role TEXT NOT NULL DEFAULT 'member' CHECK (role IN ('owner','member','viewer','admin')),
          plan TEXT NOT NULL DEFAULT 'free' CHECK (plan IN ('free','pro','team','enterprise')),
          auth_provider TEXT NOT NULL CHECK (auth_provider IN ('email','google','github')),
          auth_provider_id TEXT NOT NULL, email_verified BOOLEAN NOT NULL DEFAULT FALSE,
          schema_version TEXT NOT NULL DEFAULT '1.0',
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          last_login_at TIMESTAMPTZ, UNIQUE (auth_provider, auth_provider_id) );
    """)
    op.execute("ALTER TABLE projects ADD CONSTRAINT fk_projects_owner FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE RESTRICT;")


def downgrade() -> None:
    op.execute("ALTER TABLE projects DROP CONSTRAINT IF EXISTS fk_projects_owner;")
    op.execute("DROP TABLE IF EXISTS users;")

