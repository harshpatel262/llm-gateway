"""Gateway HTTP surface.

Request path: authenticate -> rate limit -> semantic cache lookup ->
route with retries/failover -> record cost -> cache store. Every stage
is observable via /metrics.
"""

from __future__ import annotations

from fastapi import FastAPI, Header, HTTPException, Response

from llm_gateway import __version__
from llm_gateway.budget import BudgetPolicy
from llm_gateway.cache import SemanticCache
from llm_gateway.config import Settings, get_settings
from llm_gateway.costs import CostTracker, estimate_cost
from llm_gateway.providers.base import ChatRequest, ChatResponse, Provider
from llm_gateway.providers.mock import MockProvider
from llm_gateway.ratelimit import RateLimiter
from llm_gateway.router import AllTargetsFailedError, Router, Target


def build_router(settings: Settings) -> Router:
    providers: dict[str, Provider] = {"mock": MockProvider()}
    routes: dict[str, list[Target]]

    if settings.mock_mode or not (settings.anthropic_api_key or settings.openai_api_key):
        routes = {
            "default": [Target("mock", "mock-large")],
            "fast": [Target("mock", "mock-small")],
        }
    else:
        from llm_gateway.providers.anthropic import AnthropicProvider
        from llm_gateway.providers.openai import OpenAIProvider

        default_targets: list[Target] = []
        fast_targets: list[Target] = []
        if settings.anthropic_api_key:
            providers["anthropic"] = AnthropicProvider(settings.anthropic_api_key)
            default_targets.append(Target("anthropic", "claude-sonnet-4-6"))
            fast_targets.append(Target("anthropic", "claude-haiku-4-5"))
        if settings.openai_api_key:
            providers["openai"] = OpenAIProvider(settings.openai_api_key)
            default_targets.append(Target("openai", "gpt-4o"))
            fast_targets.append(Target("openai", "gpt-4o-mini"))
        routes = {"default": default_targets, "fast": fast_targets}

    return Router(
        providers=providers,
        routes=routes,
        retry_attempts=settings.retry_attempts,
        breaker_failure_threshold=settings.breaker_failure_threshold,
        breaker_cooldown_seconds=settings.breaker_cooldown_seconds,
    )


def create_app(settings: Settings | None = None, router: Router | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="LLM Gateway", version=__version__)

    router = router or build_router(settings)
    cache = SemanticCache(
        ttl_seconds=settings.cache_ttl_seconds,
        threshold=settings.cache_similarity_threshold,
        max_entries=settings.cache_max_entries,
    )
    limiter = RateLimiter(limits=settings.client_keys)
    costs = CostTracker()
    budget = BudgetPolicy(caps=settings.client_budgets, mode=settings.budget_enforcement)

    def authenticate(api_key: str | None) -> str:
        if not api_key or api_key not in settings.client_keys:
            raise HTTPException(status_code=401, detail="invalid or missing X-API-Key")
        return api_key

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "version": __version__}

    @app.post("/v1/chat")
    async def chat(
        request: ChatRequest,
        response: Response,
        x_api_key: str | None = Header(default=None),
    ) -> ChatResponse:
        client = authenticate(x_api_key)
        if not limiter.allow(client):
            raise HTTPException(status_code=429, detail="rate limit exceeded")

        spent = costs.cost_usd.get(client, 0.0)
        if budget.should_block(client, spent):
            raise HTTPException(
                status_code=402,
                detail=f"budget exceeded: ${spent:.4f} of ${budget.caps[client]:.2f}",
            )
        response.headers["X-Budget-Status"] = budget.status(client, spent)

        cached = cache.get(request.model, request.messages)
        if cached is not None:
            return cached

        try:
            response = await router.complete(request)
        except AllTargetsFailedError as exc:
            raise HTTPException(status_code=502, detail=exc.errors) from exc

        response.cost_usd = round(estimate_cost(response.model, response.usage), 6)
        costs.record(client, response.model, response.usage)
        cache.put(request.model, request.messages, response)
        return response

    @app.get("/metrics")
    def metrics(x_api_key: str | None = Header(default=None)) -> dict:
        authenticate(x_api_key)
        budgets = {
            key: {
                "cap_usd": cap,
                "spent_usd": round(costs.cost_usd.get(key, 0.0), 6),
                "remaining_usd": round(budget.remaining(key, costs.cost_usd.get(key, 0.0)), 6),
                "status": budget.status(key, costs.cost_usd.get(key, 0.0)),
            }
            for key, cap in budget.caps.items()
        }
        return {
            "cache": {"hits": cache.hits, "misses": cache.misses},
            "clients": costs.snapshot(),
            "budgets": {"mode": budget.mode, "clients": budgets},
            "circuit_breakers": router.breaker_snapshot(),
        }

    return app


app = create_app()
