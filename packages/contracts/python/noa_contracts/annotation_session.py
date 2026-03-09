from __future__ import annotations

from typing import Literal, Any
from pydantic import BaseModel


class PlanEdit(BaseModel):
    model_config = {"extra": "allow"}


class AnnotationSession(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    id: str
    project_id: str
    parsed_plan_id: str
    user_id: str
    status: Literal["open", "submitted", "applying", "applied", "rejected"]
    trigger: Literal["ambiguity_flag", "user_initiated", "critique_failure"]
    edits: list[PlanEdit]
    submitted_at: str | None
    applied_at: str | None
    downstream_recomputed: bool
    export_to_training: bool
    created_at: str
    updated_at: str
