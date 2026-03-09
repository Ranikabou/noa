from __future__ import annotations

from typing import Literal, Any
from pydantic import BaseModel


class InspirationItem(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    id: str
    board_id: str
    source_type: Literal["upload", "curated", "url_import"]
    storage_key: str | None
    source_url: str | None
    thumbnail_key: str | None
    embedding: list[float] | None
    embedding_model: Literal["clip-vit-l-14"] | None
    weight: float
    sentiment: Literal["positive", "negative"]
    annotations: list[dict[str, Any]]
    highlighted_elements: list[dict[str, Any]]
    rejected_elements: list[dict[str, Any]]
    upload_status: Literal["pending", "ready", "failed"]
    created_at: str
