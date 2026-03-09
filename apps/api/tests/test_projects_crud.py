"""Project CRUD: POST creates, GET returns Project contract."""
from fastapi.testclient import TestClient

from noa_api.main import app

client = TestClient(app)


def test_create_project_returns_201():
    r = client.post("/v1/projects?name=Demo&owner_id=00000000-0000-0000-0000-000000000001")
    assert r.status_code == 201
    data = r.json()
    assert data["schema_version"] == "1.0"
    assert data["name"] == "Demo"
    assert data["status"] == "draft"
    assert data["id"] is not None


def test_get_project_returns_project():
    r = client.post("/v1/projects?name=GetTest&owner_id=00000000-0000-0000-0000-000000000002")
    assert r.status_code == 201
    pid = r.json()["id"]
    r2 = client.get(f"/v1/projects/{pid}")
    assert r2.status_code == 200
    assert r2.json()["id"] == pid
    assert r2.json()["name"] == "GetTest"


def test_get_project_404():
    r = client.get("/v1/projects/00000000-0000-0000-0000-000000000099")
    assert r.status_code == 404
