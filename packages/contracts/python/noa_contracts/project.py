from __future__ import annotations

from typing import Literal
from pydantic import BaseModel


class Project(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    id: str
    name: str
    owner_id: str
    status: Literal["draft", "processing", "ready", "error"]
    floorplan_asset_id: str | None
    inspiration_board_id: str | None
    canonical_model_id: str | None
    metadata: dict[str, object] = {}
    created_at: str
    updated_at: str
