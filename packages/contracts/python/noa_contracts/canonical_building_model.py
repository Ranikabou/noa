from __future__ import annotations

from typing import Literal, Any
from pydantic import BaseModel

from noa_contracts.common import ObservationType


class Level(BaseModel):
    id: str
    model_config = {"extra": "allow"}


class Wall(BaseModel):
    id: str
    model_config = {"extra": "allow"}


class Slab(BaseModel):
    id: str
    model_config = {"extra": "allow"}


class RoofElement(BaseModel):
    id: str
    model_config = {"extra": "allow"}


class Door(BaseModel):
    id: str
    model_config = {"extra": "allow"}


class Window(BaseModel):
    id: str
    model_config = {"extra": "allow"}


class Stair(BaseModel):
    id: str
    model_config = {"extra": "allow"}


class Column(BaseModel):
    id: str
    model_config = {"extra": "allow"}


class Beam(BaseModel):
    id: str
    model_config = {"extra": "allow"}


class Room(BaseModel):
    id: str
    model_config = {"extra": "allow"}


class MeshRef(BaseModel):
    id: str
    model_config = {"extra": "allow"}


class Primitive(BaseModel):
    id: str
    model_config = {"extra": "allow"}


class ElementProvenance(BaseModel):
    element_id: str
    model_config = {"extra": "allow"}


class Elements(BaseModel):
    levels: list[Level]
    walls: list[Wall]
    slabs: list[Slab]
    roofs: list[RoofElement]
    doors: list[Door]
    windows: list[Window]
    stairs: list[Stair]
    columns: list[Column]
    beams: list[Beam]
    rooms: list[Room]


class GeometryLayer(BaseModel):
    meshes: list[MeshRef]
    parametric_primitives: list[Primitive]


class CanonicalBuildingModel(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    id: str
    project_id: str
    spatial_graph_id: str
    style_profile_id: str | None
    elements: Elements
    geometry_layer: GeometryLayer
    provenance: list[ElementProvenance]
    observation_types: dict[str, ObservationType]
    version: int
    created_at: str
    updated_at: str
