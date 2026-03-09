"""Seed dev user for local development.

Revision ID: 0008
Revises: 0007
Create Date: 2025-01-01 00:00:08

"""
from typing import Sequence, Union
from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEV_USER_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    # Seed dev user for local development (owner_id in project creation)
    op.execute(f"""
        INSERT INTO users (id, email, display_name, auth_provider, auth_provider_id)
        VALUES ('{DEV_USER_ID}', 'dev@noa.local', 'Dev User', 'email', 'dev-local')
        ON CONFLICT (id) DO NOTHING;
    """)


def downgrade() -> None:
    op.execute(f"DELETE FROM users WHERE id = '{DEV_USER_ID}';")
