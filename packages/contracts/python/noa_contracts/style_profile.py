from __future__ import annotations

from typing import Literal
from pydantic import BaseModel


class MaterialPaletteEntry(BaseModel):
    name: str
    model_config = {"extra": "allow"}


class StyleSignals(BaseModel):
    massing_tendency: str
    facade_rhythm: str
    material_palette: list[MaterialPaletteEntry]
    lighting_mood: str
    surface_language: str
    compositional_balance: Literal["symmetric", "asymmetric", "dynamic"]
    emotional_tone: list[str]
    negative_preferences: list[str]
    roof_tendency: str
    glazing_ratio: float
    overhang_tendency: Literal["deep", "minimal", "none"]


class StyleProfile(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    id: str
    inspiration_board_id: str
    inference_job_id: str
    embedding_vector: list[float]
    style_signals: StyleSignals
    confidence_per_signal: dict[str, float]
    source_image_ids: list[str]
    created_at: str
