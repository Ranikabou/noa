from __future__ import annotations

from typing import Literal
from pydantic import BaseModel


class InspirationBoard(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    id: str
    project_id: str
    name: str
    description: str | None
    item_count: int
    is_primary: bool
    style_profile_id: str | None
    style_inference_status: Literal[
        "pending", "running", "ready", "stale", "failed"
    ]
    created_at: str
    updated_at: str
