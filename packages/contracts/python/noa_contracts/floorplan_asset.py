from __future__ import annotations

from typing import Literal
from pydantic import BaseModel

from noa_contracts.common import ScaleInfo


class DimensionsPx(BaseModel):
    width: int
    height: int


class FloorplanAsset(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    id: str
    project_id: str
    source_type: Literal["pdf", "image", "cad_export", "scan", "hand_marked"]
    storage_key: str
    original_filename: str
    mime_type: str
    file_size_bytes: int
    dimensions_px: DimensionsPx | None
    page_count: int
    detected_scale: ScaleInfo | None
    upload_status: Literal["pending", "ready", "failed"]
    ingestion_job_id: str | None
    created_at: str
