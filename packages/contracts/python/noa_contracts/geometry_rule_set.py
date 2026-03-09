from __future__ import annotations

from typing import Literal, Union
from pydantic import BaseModel


class GlazingRatioRule(BaseModel):
    rule_type: Literal["glazing_ratio"] = "glazing_ratio"
    target_ratio: float
    applies_to: Literal["exterior_walls", "all_walls"]
    confidence: float


class RoofRule(BaseModel):
    rule_type: Literal["roof_form"] = "roof_form"
    form: Literal["flat", "shed", "gabled", "hipped", "butterfly"]
    pitch_degrees: float | None
    confidence: float


class OverhangRule(BaseModel):
    rule_type: Literal["overhang"] = "overhang"
    model_config = {"extra": "allow"}


class FacadeGridRule(BaseModel):
    rule_type: Literal["facade_grid"] = "facade_grid"
    model_config = {"extra": "allow"}


class FloorHeightRule(BaseModel):
    rule_type: Literal["floor_height"] = "floor_height"
    model_config = {"extra": "allow"}


class MaterialHintRule(BaseModel):
    rule_type: Literal["material_hint"] = "material_hint"
    model_config = {"extra": "allow"}


GeometryRule = Union[
    GlazingRatioRule, OverhangRule, RoofRule,
    FacadeGridRule, FloorHeightRule, MaterialHintRule,
]


class GeometryRuleSet(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    id: str
    style_profile_id: str
    derived_at: str
    confidence_overall: float
    rules: list[GeometryRule]
