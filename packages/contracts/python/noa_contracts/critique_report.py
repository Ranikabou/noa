from __future__ import annotations

from typing import Literal
from pydantic import BaseModel


class CritiqueIssue(BaseModel):
    code: str
    message: str
    severity: str
    element_id: str | None = None
    model_config = {"extra": "allow"}


class CritiqueScores(BaseModel):
    plan_fidelity: float
    inspiration_alignment: float
    architectural_plausibility: float
    geometric_consistency: float
    render_coherence: float


class CritiqueReport(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    id: str
    canonical_model_id: str
    critique_job_id: str
    scores: CritiqueScores
    issues: list[CritiqueIssue]
    suggestions: list[str]
    blocking: bool
    created_at: str
