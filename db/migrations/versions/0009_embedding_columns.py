"""Embedding columns for inspiration_items and render_outputs.

The taste manifold compares corpus images (inspiration items) against render
candidates, so both need a stored CLIP embedding in the same space. Previously the
only embedding was style_profiles.embedding_vector (written as a zero vector).

Revision ID: 0009
Revises: 0008
Create Date: 2025-01-01 00:00:09

"""
from typing import Sequence, Union
from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE inspiration_items
          ADD COLUMN IF NOT EXISTS embedding JSONB,
          ADD COLUMN IF NOT EXISTS embedding_model TEXT;
    """)
    op.execute("""
        ALTER TABLE render_outputs
          ADD COLUMN IF NOT EXISTS embedding JSONB,
          ADD COLUMN IF NOT EXISTS embedding_model TEXT;
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE inspiration_items DROP COLUMN IF EXISTS embedding, DROP COLUMN IF EXISTS embedding_model;")
    op.execute("ALTER TABLE render_outputs DROP COLUMN IF EXISTS embedding, DROP COLUMN IF EXISTS embedding_model;")
