import pytest
from fastapi.testclient import TestClient

from llm_gateway.config import Settings
from llm_gateway.main import create_app


@pytest.fixture
def client() -> TestClient:
    settings = Settings(mock_mode=True, client_keys={"team-a": 60, "tiny": 1})
    return TestClient(create_app(settings=settings))


def _chat(client: TestClient, key: str, text: str = "hello world"):
    return client.post(
        "/v1/chat",
        headers={"X-API-Key": key},
        json={"model": "default", "messages": [{"role": "user", "content": text}]},
    )


def test_missing_key_is_unauthorized(client):
    response = client.post(
        "/v1/chat", json={"model": "default", "messages": [{"role": "user", "content": "hi"}]}
    )
    assert response.status_code == 401


def test_chat_round_trip(client):
    response = _chat(client, "team-a")
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "mock"
    assert body["cached"] is False


def test_repeat_request_served_from_cache(client):
    first = _chat(client, "team-a", "what is the refund policy")
    second = _chat(client, "team-a", "what is the refund policy")
    assert first.json()["cached"] is False
    assert second.json()["cached"] is True


def test_rate_limit_enforced(client):
    assert _chat(client, "tiny", "request one").status_code == 200
    assert _chat(client, "tiny", "request two").status_code == 429


def test_metrics_reports_usage(client):
    _chat(client, "team-a", "metrics probe")
    metrics = client.get("/metrics", headers={"X-API-Key": "team-a"}).json()
    assert metrics["clients"]["team-a"]["requests"] >= 1
    assert "cache" in metrics
