from __future__ import annotations

from typing import Literal
from pydantic import BaseModel


class ExportPackage(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    id: str
    canonical_model_id: str
    format: Literal["glb", "obj", "dxf", "ifc", "3dm", "blend"]
    storage_key: str
    geometry_fidelity: Literal["full", "simplified", "lod1"]
    semantic_fidelity: Literal["full", "geometry_only", "rooms_only"]
    supported_elements: list[str]
    conversion_limitations: list[str]
    export_job_id: str
    created_at: str
