"""Render scenes and render_outputs.

Revision ID: 0003
Revises: 0002
Create Date: 2025-01-01 00:00:03

"""
from typing import Sequence, Union
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE render_scenes ( id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          canonical_model_id UUID NOT NULL REFERENCES canonical_models(id),
          style_profile_id UUID REFERENCES style_profiles(id),
          cameras JSONB NOT NULL DEFAULT '[]', lighting_setup JSONB NOT NULL DEFAULT '{}',
          environment JSONB NOT NULL DEFAULT '{}', material_assignments JSONB NOT NULL DEFAULT '[]',
          render_settings JSONB NOT NULL DEFAULT '{}', variants JSONB NOT NULL DEFAULT '[]',
          schema_version TEXT NOT NULL DEFAULT '1.0', created_at TIMESTAMPTZ NOT NULL DEFAULT NOW() );
    """)
    op.execute("""
        CREATE TABLE render_outputs ( id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          render_scene_id UUID NOT NULL REFERENCES render_scenes(id) ON DELETE CASCADE,
          canonical_model_id UUID NOT NULL REFERENCES canonical_models(id),
          render_job_id UUID NOT NULL, camera_preset TEXT NOT NULL, lighting_variant TEXT NOT NULL,
          engine TEXT NOT NULL CHECK (engine IN ('eevee','cycles')),
          resolution_width INT NOT NULL, resolution_height INT NOT NULL,
          storage_key_jpeg TEXT, storage_key_png TEXT,
          file_size_bytes_jpeg BIGINT, file_size_bytes_png BIGINT, render_duration_ms INT,
          niqe_score FLOAT, pixel_coverage FLOAT, inspiration_alignment FLOAT,
          status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','rendering','ready','failed')),
          error_message TEXT, schema_version TEXT NOT NULL DEFAULT '1.0',
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW() );
    """)
    op.execute("CREATE INDEX idx_render_outputs_scene ON render_outputs(render_scene_id);")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS render_outputs;")
    op.execute("DROP TABLE IF EXISTS render_scenes;")

