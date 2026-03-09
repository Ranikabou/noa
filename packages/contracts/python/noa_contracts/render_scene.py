from __future__ import annotations

from typing import Literal, Any
from pydantic import BaseModel


class Camera(BaseModel):
    id: str
    model_config = {"extra": "allow"}


class RenderScene(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    id: str
    canonical_model_id: str
    style_profile_id: str | None
    cameras: list[Camera]
    lighting_setup: dict[str, Any]
    environment: dict[str, Any]
    material_assignments: list[dict[str, Any]]
    render_settings: dict[str, Any]  # engine, samples, resolution, output_formats
    variants: list[dict[str, Any]]
    created_at: str
