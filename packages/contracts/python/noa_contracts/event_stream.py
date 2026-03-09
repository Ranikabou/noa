from __future__ import annotations

from typing import Literal
from pydantic import BaseModel


class JobUpdateData(BaseModel):
    job_id: str
    job_type: str
    status: Literal["queued", "running", "complete", "failed", "retrying"]
    retry_count: int
    progress: float
    stage: str | None
    result_ref: str | None
    error: dict[str, str] | None
    timestamp: str


class JobUpdateEvent(BaseModel):
    event: Literal["job_update"] = "job_update"
    data: JobUpdateData


class AmbiguityFlagData(BaseModel):
    flag_id: str
    element_type: str
    description: str
    confidence: float
    requires_user_action: bool
    timestamp: str


class AmbiguityFlagEvent(BaseModel):
    event: Literal["ambiguity_flag"] = "ambiguity_flag"
    data: AmbiguityFlagData


class HeartbeatEvent(BaseModel):
    event: Literal["heartbeat"] = "heartbeat"
    data: dict[str, str]  # timestamp
