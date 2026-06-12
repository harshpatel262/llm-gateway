from __future__ import annotations

from llm_gateway.providers.base import (
    ChatRequest,
    ChatResponse,
    Provider,
    ProviderError,
    Usage,
)


class MockProvider(Provider):
    """Offline provider for tests and keyless demos. Can be configured to
    fail to exercise the router's failover and circuit-breaker paths."""

    def __init__(self, name: str = "mock", fail: bool = False):
        self.name = name
        self.fail = fail
        self.calls = 0

    async def complete(self, request: ChatRequest, model: str) -> ChatResponse:
        self.calls += 1
        if self.fail:
            raise ProviderError(f"{self.name}: simulated upstream failure")
        prompt = request.messages[-1].content
        return ChatResponse(
            text=f"[{self.name}/{model}] echo: {prompt[:200]}",
            provider=self.name,
            model=model,
            usage=Usage(input_tokens=len(prompt.split()), output_tokens=12),
        )
