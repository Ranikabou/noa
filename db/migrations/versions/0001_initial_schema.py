"""Initial schema — projects, floorplan_assets, parsed_plans, inspiration, style, spatial, canonical, agent_outputs, critique, export.

Revision ID: 0001
Revises:
Create Date: 2025-01-01 00:00:01

"""
from typing import Sequence, Union
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto";')
    op.execute('CREATE EXTENSION IF NOT EXISTS "vector";')
    op.execute("""
        CREATE TABLE projects (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          name TEXT NOT NULL, owner_id UUID NOT NULL,
          status TEXT NOT NULL DEFAULT 'draft'
            CHECK (status IN ('draft','processing','ready','error')),
          floorplan_asset_id UUID, inspiration_board_id UUID, canonical_model_id UUID,
          metadata JSONB NOT NULL DEFAULT '{}', schema_version TEXT NOT NULL DEFAULT '1.0',
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)
    op.execute("""
        CREATE TABLE floorplan_assets (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
          source_type TEXT NOT NULL, storage_key TEXT NOT NULL UNIQUE,
          original_filename TEXT NOT NULL, mime_type TEXT NOT NULL,
          file_size_bytes BIGINT NOT NULL, dimensions_px JSONB, page_count INT NOT NULL DEFAULT 1,
          detected_scale JSONB, upload_status TEXT NOT NULL DEFAULT 'pending',
          ingestion_job_id UUID, schema_version TEXT NOT NULL DEFAULT '1.0',
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)
    op.execute("""
        CREATE TABLE parsed_plans (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          floorplan_asset_id UUID NOT NULL REFERENCES floorplan_assets(id),
          parse_job_id UUID NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
          confidence_overall FLOAT, ambiguity_flags JSONB NOT NULL DEFAULT '[]',
          walls JSONB NOT NULL DEFAULT '[]', openings JSONB NOT NULL DEFAULT '[]',
          rooms JSONB NOT NULL DEFAULT '[]', stairs JSONB NOT NULL DEFAULT '[]',
          columns JSONB NOT NULL DEFAULT '[]', annotations JSONB NOT NULL DEFAULT '[]',
          bounding_box_px JSONB, coordinate_origin JSONB,
          schema_version TEXT NOT NULL DEFAULT '1.0', created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)
    op.execute("""
        CREATE TABLE inspiration_boards (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
          name TEXT NOT NULL DEFAULT 'My Board', description TEXT,
          item_count INT NOT NULL DEFAULT 0, is_primary BOOLEAN NOT NULL DEFAULT FALSE,
          style_profile_id UUID,
          style_inference_status TEXT NOT NULL DEFAULT 'pending'
            CHECK (style_inference_status IN ('pending','running','ready','stale','failed')),
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)
    op.execute("""
        CREATE TABLE inspiration_items (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          board_id UUID NOT NULL REFERENCES inspiration_boards(id) ON DELETE CASCADE,
          source_type TEXT NOT NULL CHECK (source_type IN ('upload','curated','url_import')),
          storage_key TEXT, source_url TEXT, thumbnail_key TEXT,
          embedding vector(768), embedding_model TEXT,
          weight FLOAT NOT NULL DEFAULT 1.0, sentiment TEXT NOT NULL DEFAULT 'positive'
            CHECK (sentiment IN ('positive','negative')),
          annotations JSONB NOT NULL DEFAULT '[]',
          highlighted_elements JSONB NOT NULL DEFAULT '[]',
          rejected_elements JSONB NOT NULL DEFAULT '[]',
          upload_status TEXT NOT NULL DEFAULT 'pending',
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)
    op.execute("CREATE INDEX idx_inspiration_items_embedding ON inspiration_items USING ivfflat (embedding vector_cosine_ops);")
    op.execute("""
        CREATE TABLE style_profiles ( id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          inspiration_board_id UUID NOT NULL REFERENCES inspiration_boards(id),
          inference_job_id UUID NOT NULL, embedding_vector vector(768),
          style_signals JSONB NOT NULL, confidence_per_signal JSONB NOT NULL,
          source_image_ids UUID[] NOT NULL,
          schema_version TEXT NOT NULL DEFAULT '1.0', created_at TIMESTAMPTZ NOT NULL DEFAULT NOW() );
    """)
    op.execute("""
        CREATE TABLE spatial_graphs ( id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          parsed_plan_id UUID NOT NULL REFERENCES parsed_plans(id),
          nodes JSONB NOT NULL DEFAULT '[]', edges JSONB NOT NULL DEFAULT '[]',
          levels JSONB NOT NULL DEFAULT '[]', circulation_graph JSONB NOT NULL DEFAULT '{}',
          room_adjacency_matrix JSONB, scale_meters_per_unit FLOAT NOT NULL DEFAULT 1.0,
          coordinate_system TEXT NOT NULL DEFAULT 'metric',
          schema_version TEXT NOT NULL DEFAULT '1.0', created_at TIMESTAMPTZ NOT NULL DEFAULT NOW() );
    """)
    op.execute("""
        CREATE TABLE canonical_models ( id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          project_id UUID NOT NULL REFERENCES projects(id),
          spatial_graph_id UUID REFERENCES spatial_graphs(id),
          style_profile_id UUID REFERENCES style_profiles(id),
          elements JSONB NOT NULL DEFAULT '{}', geometry_layer JSONB NOT NULL DEFAULT '{}',
          provenance JSONB NOT NULL DEFAULT '[]', observation_types JSONB NOT NULL DEFAULT '{}',
          version INT NOT NULL DEFAULT 1, schema_version TEXT NOT NULL DEFAULT '1.0',
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW() );
    """)
    op.execute("""
        CREATE TABLE agent_outputs ( id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          job_id UUID NOT NULL, agent_name TEXT NOT NULL, input_hash TEXT NOT NULL,
          output JSONB NOT NULL, duration_ms INT, model_used TEXT,
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW() );
    """)
    op.execute("CREATE INDEX idx_agent_outputs_job ON agent_outputs(job_id);")
    op.execute("""
        CREATE TABLE critique_reports ( id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          canonical_model_id UUID NOT NULL REFERENCES canonical_models(id),
          critique_job_id UUID NOT NULL, scores JSONB NOT NULL,
          issues JSONB NOT NULL DEFAULT '[]', suggestions JSONB NOT NULL DEFAULT '[]',
          blocking BOOLEAN NOT NULL DEFAULT FALSE,
          schema_version TEXT NOT NULL DEFAULT '1.0', created_at TIMESTAMPTZ NOT NULL DEFAULT NOW() );
    """)
    op.execute("""
        CREATE TABLE export_packages ( id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          canonical_model_id UUID NOT NULL REFERENCES canonical_models(id),
          format TEXT NOT NULL, storage_key TEXT NOT NULL,
          geometry_fidelity TEXT NOT NULL, semantic_fidelity TEXT NOT NULL,
          supported_elements TEXT[] NOT NULL, limitations TEXT[] NOT NULL,
          export_job_id UUID NOT NULL, schema_version TEXT NOT NULL DEFAULT '1.0',
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW() );
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS export_packages;")
    op.execute("DROP TABLE IF EXISTS critique_reports;")
    op.execute("DROP TABLE IF EXISTS agent_outputs;")
    op.execute("DROP TABLE IF EXISTS canonical_models;")
    op.execute("DROP TABLE IF EXISTS spatial_graphs;")
    op.execute("DROP TABLE IF EXISTS style_profiles;")
    op.execute("DROP TABLE IF EXISTS inspiration_items;")
    op.execute("DROP TABLE IF EXISTS inspiration_boards;")
    op.execute("DROP TABLE IF EXISTS parsed_plans;")
    op.execute("DROP TABLE IF EXISTS floorplan_assets;")
    op.execute("DROP TABLE IF EXISTS projects;")
