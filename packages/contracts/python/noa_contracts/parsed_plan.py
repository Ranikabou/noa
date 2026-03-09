from __future__ import annotations

from typing import Literal, Any
from pydantic import BaseModel

from noa_contracts.common import BBox, Point2D, ObservationType


class ParsedWall(BaseModel):
    id: str
    geometry: list[list[float]]
    confidence: float
    observation_type: ObservationType


class ParsedOpening(BaseModel):
    id: str
    geometry: list[list[float]]
    confidence: float
    observation_type: ObservationType


class ParsedRoom(BaseModel):
    id: str
    geometry: list[list[float]]
    confidence: float
    observation_type: ObservationType


class ParsedStair(BaseModel):
    id: str
    geometry: Any
    confidence: float
    observation_type: ObservationType


class ParsedColumn(BaseModel):
    id: str
    geometry: Any
    confidence: float
    observation_type: ObservationType


class ParsedAnnotation(BaseModel):
    id: str
    geometry: Any
    confidence: float
    observation_type: ObservationType


class AmbiguityFlag(BaseModel):
    id: str
    element_type: str
    description: str
    confidence: float
    element_id: str | None = None


class ParsedPlan(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    id: str
    floorplan_asset_id: str
    parse_job_id: str
    status: Literal["pending", "partial", "complete", "failed"]
    confidence_overall: float
    ambiguity_flags: list[AmbiguityFlag]
    walls: list[ParsedWall]
    openings: list[ParsedOpening]
    rooms: list[ParsedRoom]
    stairs: list[ParsedStair]
    columns: list[ParsedColumn]
    annotations: list[ParsedAnnotation]
    bounding_box_px: BBox
    coordinate_origin: Point2D
    created_at: str
