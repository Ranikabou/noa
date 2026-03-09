from __future__ import annotations

from typing import Literal
from pydantic import BaseModel


class QualityScores(BaseModel):
    niqe: float | None
    pixel_coverage: float | None
    inspiration_alignment: float | None


class RenderImage(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    id: str
    render_scene_id: str
    canonical_model_id: str
    render_job_id: str
    camera_preset: Literal[
        "exterior_3q", "exterior_street", "aerial_45", "courtyard", "interior_living"
    ]
    lighting_variant: Literal["midday", "golden_hour", "overcast", "dusk", "night"]
    engine: Literal["eevee", "cycles"]
    resolution: dict[str, int]
    storage_key_jpeg: str | None
    storage_key_png: str | None
    render_duration_ms: int | None
    quality_scores: QualityScores
    status: Literal["pending", "rendering", "ready", "failed"]
    error_message: str | None
    created_at: str
    updated_at: str
