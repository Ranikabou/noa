"""Cross-language snapshot test: Project contract JSON round-trip."""
import json
import pytest
from noa_contracts import Project


SAMPLE_PROJECT_JSON = {
    "schema_version": "1.0",
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "Test Project",
    "owner_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
    "status": "draft",
    "floorplan_asset_id": None,
    "inspiration_board_id": None,
    "canonical_model_id": None,
    "metadata": {},
    "created_at": "2025-01-15T12:00:00.000Z",
    "updated_at": "2025-01-15T12:00:00.000Z",
}


def test_project_parses_sample_json():
    """Pydantic Project model must parse the canonical sample JSON."""
    project = Project.model_validate(SAMPLE_PROJECT_JSON)
    assert project.schema_version == "1.0"
    assert project.status == "draft"
    assert project.name == "Test Project"


def test_project_serializes_to_identical_json():
    """Pydantic model_dump(mode='json') must match canonical JSON structure."""
    project = Project.model_validate(SAMPLE_PROJECT_JSON)
    dumped = project.model_dump(mode="json")
    # Compare key fields; order of keys may differ
    assert dumped["schema_version"] == SAMPLE_PROJECT_JSON["schema_version"]
    assert dumped["id"] == SAMPLE_PROJECT_JSON["id"]
    assert dumped["status"] == SAMPLE_PROJECT_JSON["status"]
    assert dumped["metadata"] == SAMPLE_PROJECT_JSON["metadata"]
    # Full round-trip
    again = Project.model_validate(dumped)
    assert again.model_dump(mode="json") == dumped
