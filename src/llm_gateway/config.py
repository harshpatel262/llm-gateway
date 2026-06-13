from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GATEWAY_", env_file=".env", extra="ignore")

    anthropic_api_key: str | None = None
    openai_api_key: str | None = None

    # client API keys accepted by the gateway, each with a requests/minute cap.
    # JSON in env, e.g. GATEWAY_CLIENT_KEYS='{"team-a": 120, "team-b": 30}'
    client_keys: dict[str, int] = {"demo-key": 60}

    cache_ttl_seconds: int = 300
    cache_similarity_threshold: float = 0.97
    cache_max_entries: int = 1024

    # circuit breaker: open a target after N consecutive failures, for M seconds
    breaker_failure_threshold: int = 3
    breaker_cooldown_seconds: float = 30.0
    retry_attempts: int = 2

    # spend cap (USD) per client key over the accounting window. JSON in env,
    # e.g. GATEWAY_CLIENT_BUDGETS='{"team-a": 500.0}'. Clients absent from the
    # map are uncapped.
    client_budgets: dict[str, float] = {}
    # "off" never blocks; "soft" allows but flags over-budget clients via the
    # X-Budget-Status header; "hard" returns 402 once a client is over its cap.
    budget_enforcement: str = "soft"

    # route every request to the offline mock provider (demos / tests)
    mock_mode: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
