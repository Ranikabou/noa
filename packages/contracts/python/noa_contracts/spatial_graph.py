from __future__ import annotations

from typing import Literal, Any
from pydantic import BaseModel


class SpatialNode(BaseModel):
    id: str
    model_config = {"extra": "allow"}


class SpatialEdge(BaseModel):
    id: str
    model_config = {"extra": "allow"}


class LevelDescriptor(BaseModel):
    id: str
    model_config = {"extra": "allow"}


class SpatialGraph(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    id: str
    parsed_plan_id: str
    nodes: list[SpatialNode]
    edges: list[SpatialEdge]
    levels: list[LevelDescriptor]
    circulation_graph: dict[str, Any]
    room_adjacency_matrix: list[list[float]]
    scale_meters_per_unit: float = 1.0
    coordinate_system: Literal["metric", "imperial"] = "metric"
    created_at: str
