"""Smoke tests for health/readiness routes.

Validates the scaffold boots and the cheap probes respond. Expand in the next pass.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_ok() -> None:
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["service"] == "county-assistant"


def test_ready_ok() -> None:
    resp = client.get("/api/ready")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"


def test_root_banner() -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["service"] == "county-assistant"
