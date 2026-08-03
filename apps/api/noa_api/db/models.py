"""SQLAlchemy models matching blueprint schema."""
from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def _uuid():
    return str(uuid4())


class User(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    email = Column(Text, nullable=False, unique=True)
    display_name = Column(Text, nullable=False)
    avatar_url = Column(Text)
    role = Column(Text, nullable=False, default="member")
    plan = Column(Text, nullable=False, default="free")
    auth_provider = Column(Text, nullable=False)
    auth_provider_id = Column(Text, nullable=False)
    email_verified = Column(Boolean, nullable=False, default=False)
    schema_version = Column(Text, nullable=False, default="1.0")
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login_at = Column(DateTime(timezone=True))


class Project(Base):
    __tablename__ = "projects"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    name = Column(Text, nullable=False)
    owner_id = Column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    status = Column(Text, nullable=False, default="draft")
    floorplan_asset_id = Column(UUID(as_uuid=False))  # References floorplan_assets.id, no FK in schema
    inspiration_board_id = Column(UUID(as_uuid=False))
    canonical_model_id = Column(UUID(as_uuid=False))
    metadata_ = Column("metadata", JSONB, nullable=False, default=dict)
    schema_version = Column(Text, nullable=False, default="1.0")
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class FloorplanAsset(Base):
    __tablename__ = "floorplan_assets"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    project_id = Column(UUID(as_uuid=False), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    source_type = Column(Text, nullable=False)
    storage_key = Column(Text, nullable=False, unique=True)
    original_filename = Column(Text, nullable=False)
    mime_type = Column(Text, nullable=False)
    file_size_bytes = Column(BigInteger, nullable=False)
    dimensions_px = Column(JSONB)
    page_count = Column(Integer, nullable=False, default=1)
    detected_scale = Column(JSONB)
    upload_status = Column(Text, nullable=False, default="pending")
    ingestion_job_id = Column(UUID(as_uuid=False))
    schema_version = Column(Text, nullable=False, default="1.0")
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class ParsedPlan(Base):
    __tablename__ = "parsed_plans"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    floorplan_asset_id = Column(UUID(as_uuid=False), ForeignKey("floorplan_assets.id"), nullable=False)
    parse_job_id = Column(UUID(as_uuid=False), nullable=False)
    status = Column(Text, nullable=False, default="pending")
    confidence_overall = Column(Float)
    ambiguity_flags = Column(JSONB, nullable=False, default=list)
    walls = Column(JSONB, nullable=False, default=list)
    openings = Column(JSONB, nullable=False, default=list)
    rooms = Column(JSONB, nullable=False, default=list)
    stairs = Column(JSONB, nullable=False, default=list)
    columns = Column(JSONB, nullable=False, default=list)
    annotations = Column(JSONB, nullable=False, default=list)
    bounding_box_px = Column(JSONB)
    coordinate_origin = Column(JSONB)
    schema_version = Column(Text, nullable=False, default="1.0")
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class InspirationBoard(Base):
    __tablename__ = "inspiration_boards"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    project_id = Column(UUID(as_uuid=False), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name = Column(Text, nullable=False, default="My Board")
    description = Column(Text)
    item_count = Column(Integer, nullable=False, default=0)
    is_primary = Column(Boolean, nullable=False, default=False)
    style_profile_id = Column(UUID(as_uuid=False))
    style_inference_status = Column(Text, nullable=False, default="pending")
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class InspirationItem(Base):
    __tablename__ = "inspiration_items"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    board_id = Column(UUID(as_uuid=False), ForeignKey("inspiration_boards.id", ondelete="CASCADE"), nullable=False)
    source_type = Column(Text, nullable=False, default="upload")
    storage_key = Column(Text)
    source_url = Column(Text)
    thumbnail_key = Column(Text)
    weight = Column(Float, nullable=False, default=1.0)
    sentiment = Column(Text, nullable=False, default="positive")
    embedding = Column(JSONB)  # CLIP image embedding (768-dim list), shared space with render_outputs
    embedding_model = Column(Text)
    annotations = Column(JSONB, nullable=False, default=list)
    highlighted_elements = Column(JSONB, nullable=False, default=list)
    rejected_elements = Column(JSONB, nullable=False, default=list)
    upload_status = Column(Text, nullable=False, default="pending")
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class StyleProfile(Base):
    __tablename__ = "style_profiles"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    inspiration_board_id = Column(UUID(as_uuid=False), ForeignKey("inspiration_boards.id"), nullable=False)
    inference_job_id = Column(UUID(as_uuid=False), nullable=False)
    embedding_vector = Column(JSONB)  # stored as JSON list; pgvector col exists but we use JSONB for API
    style_signals = Column(JSONB, nullable=False)
    confidence_per_signal = Column(JSONB, nullable=False)
    source_image_ids = Column(JSONB, nullable=False, default=list)
    schema_version = Column(Text, nullable=False, default="1.0")
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class GeometryRuleSet(Base):
    __tablename__ = "geometry_rule_sets"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    style_profile_id = Column(UUID(as_uuid=False), ForeignKey("style_profiles.id"), nullable=False)
    derived_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    confidence_overall = Column(Float, nullable=False)
    rules = Column(JSONB, nullable=False, default=list)
    schema_version = Column(Text, nullable=False, default="1.0")
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class CanonicalModel(Base):
    __tablename__ = "canonical_models"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    project_id = Column(UUID(as_uuid=False), ForeignKey("projects.id"), nullable=False)
    spatial_graph_id = Column(UUID(as_uuid=False))
    style_profile_id = Column(UUID(as_uuid=False))
    elements = Column(JSONB, nullable=False, default=dict)
    geometry_layer = Column(JSONB, nullable=False, default=dict)
    provenance = Column(JSONB, nullable=False, default=list)
    observation_types = Column(JSONB, nullable=False, default=dict)
    version = Column(Integer, nullable=False, default=1)
    schema_version = Column(Text, nullable=False, default="1.0")
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class RenderScene(Base):
    __tablename__ = "render_scenes"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    canonical_model_id = Column(UUID(as_uuid=False), ForeignKey("canonical_models.id"), nullable=False)
    style_profile_id = Column(UUID(as_uuid=False))
    cameras = Column(JSONB, nullable=False, default=list)
    lighting_setup = Column(JSONB, nullable=False, default=dict)
    environment = Column(JSONB, nullable=False, default=dict)
    material_assignments = Column(JSONB, nullable=False, default=list)
    render_settings = Column(JSONB, nullable=False, default=dict)
    variants = Column(JSONB, nullable=False, default=list)
    schema_version = Column(Text, nullable=False, default="1.0")
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class RenderOutput(Base):
    __tablename__ = "render_outputs"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    render_scene_id = Column(UUID(as_uuid=False), ForeignKey("render_scenes.id", ondelete="CASCADE"), nullable=False)
    canonical_model_id = Column(UUID(as_uuid=False), ForeignKey("canonical_models.id"), nullable=False)
    render_job_id = Column(UUID(as_uuid=False), nullable=False)
    camera_preset = Column(Text, nullable=False)
    lighting_variant = Column(Text, nullable=False)
    engine = Column(Text, nullable=False, default="eevee")
    resolution_width = Column(Integer, nullable=False)
    resolution_height = Column(Integer, nullable=False)
    storage_key_jpeg = Column(Text)
    storage_key_png = Column(Text)
    file_size_bytes_jpeg = Column(BigInteger)
    file_size_bytes_png = Column(BigInteger)
    render_duration_ms = Column(Integer)
    niqe_score = Column(Float)
    pixel_coverage = Column(Float)
    inspiration_alignment = Column(Float)
    embedding = Column(JSONB)  # CLIP image embedding (768-dim list), shared space with inspiration_items
    embedding_model = Column(Text)
    status = Column(Text, nullable=False, default="pending")
    error_message = Column(Text)
    schema_version = Column(Text, nullable=False, default="1.0")
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class ExportPackage(Base):
    __tablename__ = "export_packages"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    canonical_model_id = Column(UUID(as_uuid=False), ForeignKey("canonical_models.id"), nullable=False)
    format = Column(Text, nullable=False)
    storage_key = Column(Text, nullable=False)
    geometry_fidelity = Column(Text, nullable=False, default="full")
    semantic_fidelity = Column(Text, nullable=False, default="full")
    supported_elements = Column(JSONB, nullable=False, default=list)
    limitations = Column(JSONB, nullable=False, default=list)
    export_job_id = Column(UUID(as_uuid=False), nullable=False)
    schema_version = Column(Text, nullable=False, default="1.0")
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class ProjectEvent(Base):
    __tablename__ = "project_events"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    project_id = Column(UUID(as_uuid=False), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    event_type = Column(Text, nullable=False)
    sequence_no = Column(BigInteger, nullable=False)
    payload = Column(JSONB, nullable=False)
    job_id = Column(UUID(as_uuid=False))
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
