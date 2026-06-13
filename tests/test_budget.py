from fastapi.testclient import TestClient

from llm_gateway.budget import BudgetPolicy
from llm_gateway.config import Settings
from llm_gateway.main import create_app


# --- unit tests: BudgetPolicy ---

def test_uncapped_client_is_never_over():
    policy = BudgetPolicy(caps={}, mode="hard")
    assert policy.status("anyone", 999.0) == "uncapped"
    assert policy.should_block("anyone", 999.0) is False
    assert policy.remaining("anyone", 999.0) is None


def test_status_flips_at_cap():
    policy = BudgetPolicy(caps={"team-a": 10.0}, mode="soft")
    assert policy.status("team-a", 9.99) == "ok"
    assert policy.status("team-a", 10.0) == "over"
    assert policy.remaining("team-a", 7.5) == 2.5
    assert policy.remaining("team-a", 12.0) == 0.0


def test_only_hard_mode_blocks():
    over = 5.0
    assert BudgetPolicy({"c": 1.0}, "hard").should_block("c", over) is True
    assert BudgetPolicy({"c": 1.0}, "soft").should_block("c", over) is False
    assert BudgetPolicy({"c": 1.0}, "off").should_block("c", over) is False


# --- API tests ---

def _client(mode: str, caps: dict) -> TestClient:
    settings = Settings(
        mock_mode=True,
        client_keys={"team-a": 60},
        client_budgets=caps,
        budget_enforcement=mode,
    )
    return TestClient(create_app(settings=settings))


def _chat(client: TestClient, text: str = "hello"):
    return client.post(
        "/v1/chat",
        headers={"X-API-Key": "team-a"},
        json={"model": "default", "messages": [{"role": "user", "content": text}]},
    )


def test_hard_enforcement_blocks_over_budget_client():
    # cap of 0 means any recorded spend (including the starting 0) is "over"
    client = _client("hard", {"team-a": 0.0})
    response = _chat(client)
    assert response.status_code == 402
    assert "budget exceeded" in response.json()["detail"]


def test_soft_enforcement_allows_but_flags():
    client = _client("soft", {"team-a": 0.0})
    response = _chat(client)
    assert response.status_code == 200
    assert response.headers["X-Budget-Status"] == "over"


def test_within_budget_reports_ok_header():
    client = _client("hard", {"team-a": 1000.0})
    response = _chat(client)
    assert response.status_code == 200
    assert response.headers["X-Budget-Status"] == "ok"


def test_uncapped_client_has_uncapped_header():
    client = _client("hard", {})
    response = _chat(client)
    assert response.status_code == 200
    assert response.headers["X-Budget-Status"] == "uncapped"


def test_metrics_includes_budget_section():
    client = _client("soft", {"team-a": 5.0})
    _chat(client)
    metrics = client.get("/metrics", headers={"X-API-Key": "team-a"}).json()
    assert metrics["budgets"]["mode"] == "soft"
    assert metrics["budgets"]["clients"]["team-a"]["cap_usd"] == 5.0
    assert "remaining_usd" in metrics["budgets"]["clients"]["team-a"]
