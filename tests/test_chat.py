"""Tests for the chat endpoint and agent routing (local-fallback mode)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_chat_grounded_answer_has_citations() -> None:
    resp = client.post(
        "/api/chat",
        json={"message": "How do I apply for a building permit and how much does it cost?"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["answer"]
    assert body["mode"] in {"foundry", "local-fallback"}
    assert body["citations"], "expected grounding citations"
    assert resp.headers.get("X-Correlation-Id")


def test_chat_workflow_intent_short_circuits() -> None:
    resp = client.post("/api/chat", json={"message": "I want to report a pothole"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["route"].startswith("workflow:")


def test_chat_safety_emergency_redirect() -> None:
    resp = client.post("/api/chat", json={"message": "this is an emergency, someone is hurt"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["route"] == "safety:emergency"
    assert "911" in body["answer"]


def test_chat_rejects_empty_message() -> None:
    resp = client.post("/api/chat", json={"message": ""})
    assert resp.status_code == 422


def test_session_id_is_returned_and_stable() -> None:
    resp = client.post(
        "/api/chat",
        json={"message": "when is property tax due", "session_id": "abc123"},
    )
    assert resp.status_code == 200
    assert resp.json()["session_id"] == "abc123"
