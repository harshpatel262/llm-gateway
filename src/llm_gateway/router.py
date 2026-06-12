"""Routing, retries, failover, and per-target circuit breaking.

A request names a route alias ("default", "fast", ...). Each alias maps to
an ordered list of (provider, model) targets. The router tries targets in
order, retrying transient failures with exponential backoff; a target that
keeps failing gets its circuit opened and is skipped until a cooldown
elapses, so a degraded provider can't add latency to every request.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

from llm_gateway.providers.base import ChatRequest, ChatResponse, Provider, ProviderError


@dataclass(frozen=True)
class Target:
    provider: str
    model: str


@dataclass
class BreakerState:
    consecutive_failures: int = 0
    open_until: float = 0.0


class AllTargetsFailedError(Exception):
    def __init__(self, route: str, errors: list[str]):
        self.errors = errors
        super().__init__(f"route '{route}': all targets failed: {errors}")


@dataclass
class Router:
    providers: dict[str, Provider]
    routes: dict[str, list[Target]]
    retry_attempts: int = 2
    breaker_failure_threshold: int = 3
    breaker_cooldown_seconds: float = 30.0
    _breakers: dict[Target, BreakerState] = field(default_factory=dict)

    def _breaker(self, target: Target) -> BreakerState:
        return self._breakers.setdefault(target, BreakerState())

    def breaker_snapshot(self) -> dict[str, dict]:
        now = time.monotonic()
        return {
            f"{t.provider}/{t.model}": {
                "consecutive_failures": b.consecutive_failures,
                "open": b.open_until > now,
            }
            for t, b in self._breakers.items()
        }

    async def _try_target(self, target: Target, request: ChatRequest) -> ChatResponse:
        provider = self.providers[target.provider]
        last_error: Exception | None = None
        for attempt in range(self.retry_attempts + 1):
            try:
                return await provider.complete(request, target.model)
            except ProviderError as exc:
                last_error = exc
                if attempt < self.retry_attempts:
                    await asyncio.sleep(0.2 * (2**attempt))
        raise last_error  # type: ignore[misc]

    async def complete(self, request: ChatRequest) -> ChatResponse:
        route = request.model if request.model in self.routes else "default"
        targets = self.routes[route]
        now = time.monotonic()
        errors: list[str] = []

        for target in targets:
            breaker = self._breaker(target)
            if breaker.open_until > now:
                errors.append(f"{target.provider}/{target.model}: circuit open")
                continue

            try:
                response = await self._try_target(target, request)
            except ProviderError as exc:
                breaker.consecutive_failures += 1
                if breaker.consecutive_failures >= self.breaker_failure_threshold:
                    breaker.open_until = time.monotonic() + self.breaker_cooldown_seconds
                errors.append(str(exc))
                continue

            breaker.consecutive_failures = 0
            breaker.open_until = 0.0
            return response

        raise AllTargetsFailedError(route, errors)
