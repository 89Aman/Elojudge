"""Tests for API endpoints, static routing, and favicon."""

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


def test_favicon():
    response = client.get("/favicon.ico")
    assert response.status_code == 200
    assert "svg" in response.headers.get("content-type", "")
    assert b"<svg" in response.content


def test_root_index():
    response = client.get("/")
    assert response.status_code == 200
    assert b"EloJudge" in response.content
    assert b"favicon.svg" in response.content


def test_not_found():
    response = client.get("/non-existent-path-12345")
    assert response.status_code == 404
    assert b"404" in response.content


def test_auth_status_endpoint():
    response = client.get("/auth/status")
    assert response.status_code == 200
    data = response.json()
    assert "google_client_id" in data
    assert "374080008653" in data["google_client_id"]
    assert data["authenticated"] is False


def test_history_list():
    response = client.get("/history")
    assert response.status_code == 200
    data = response.json()
    assert "jobs" in data
    assert isinstance(data["jobs"], list)


def test_history_not_found():
    response = client.get("/history/job_nonexistent_999999")
    assert response.status_code == 404
