"""Health endpoint returns 200."""
from fastapi.testclient import TestClient

from noa_api.main import app

client = TestClient(app)


def test_health_returns_200():
    r = client.get("/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.json()["service"] == "noa-api"
