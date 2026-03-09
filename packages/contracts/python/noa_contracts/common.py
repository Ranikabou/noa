from __future__ import annotations

from typing import Literal
from pydantic import BaseModel


class BBox(BaseModel):
    min_x: float
    min_y: float
    max_x: float
    max_y: float


class Point2D(BaseModel):
    x: float
    y: float


class ScaleInfo(BaseModel):
    px_per_meter: float
    confidence: float
    method: Literal["barscale", "dimension_text", "known_element", "assumed"]


ObservationType = Literal["observed", "inferred", "assumed_default"]
