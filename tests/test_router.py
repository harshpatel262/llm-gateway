import pytest

from llm_gateway.providers.base import ChatMessage, ChatRequest
from llm_gateway.providers.mock import MockProvider
from llm_gateway.router import AllTargetsFailedError, Router, Target


def _request(text: str = "hello") -> ChatRequest:
    return ChatRequest(model="default", messages=[ChatMessage(role="user", content=text)])


def _router(primary_fails: bool, **kwargs) -> tuple[Router, MockProvider, MockProvider]:
    primary = MockProvider(name="primary", fail=primary_fails)
    fallback = MockProvider(name="fallback")
    router = Router(
        providers={"primary": primary, "fallback": fallback},
        routes={"default": [Target("primary", "model-a"), Target("fallback", "model-b")]},
        retry_attempts=1,
        breaker_failure_threshold=2,
        breaker_cooldown_seconds=60.0,
        **kwargs,
    )
    return router, primary, fallback


async def test_healthy_primary_serves_request():
    router, primary, fallback = _router(primary_fails=False)
    response = await router.complete(_request())
    assert response.provider == "primary"
    assert fallback.calls == 0


async def test_failover_to_secondary_target():
    router, primary, fallback = _router(primary_fails=True)
    response = await router.complete(_request())
    assert response.provider == "fallback"
    assert primary.calls == 2  # initial attempt + 1 retry


async def test_circuit_opens_and_skips_failing_target():
    router, primary, _ = _router(primary_fails=True)

    await router.complete(_request())  # failure 1 -> breaker counts retries as one failure
    await router.complete(_request())  # failure 2 -> breaker opens
    calls_before = primary.calls
    await router.complete(_request())  # breaker open -> primary not even tried

    assert primary.calls == calls_before
    snapshot = router.breaker_snapshot()
    assert snapshot["primary/model-a"]["open"] is True


async def test_all_targets_failing_raises():
    failing = MockProvider(name="only", fail=True)
    router = Router(
        providers={"only": failing},
        routes={"default": [Target("only", "model-a")]},
        retry_attempts=0,
    )
    with pytest.raises(AllTargetsFailedError):
        await router.complete(_request())


async def test_unknown_alias_falls_back_to_default_route():
    router, _, _ = _router(primary_fails=False)
    request = ChatRequest(
        model="no-such-route", messages=[ChatMessage(role="user", content="hi")]
    )
    response = await router.complete(request)
    assert response.provider == "primary"
