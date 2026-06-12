"""Per-request cost computation and per-client accounting."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from llm_gateway.providers.base import Usage

# USD per million tokens (input, output). Unknown models cost 0 — the
# gateway never blocks a request over a missing price entry.
PRICING: dict[str, tuple[float, float]] = {
    "claude-opus-4-8": (15.00, 75.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
}


def estimate_cost(model: str, usage: Usage) -> float:
    input_price, output_price = PRICING.get(model, (0.0, 0.0))
    return (usage.input_tokens * input_price + usage.output_tokens * output_price) / 1_000_000


@dataclass
class CostTracker:
    requests: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    input_tokens: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    output_tokens: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    cost_usd: dict[str, float] = field(default_factory=lambda: defaultdict(float))

    def record(self, client_key: str, model: str, usage: Usage) -> float:
        cost = estimate_cost(model, usage)
        self.requests[client_key] += 1
        self.input_tokens[client_key] += usage.input_tokens
        self.output_tokens[client_key] += usage.output_tokens
        self.cost_usd[client_key] += cost
        return cost

    def snapshot(self) -> dict:
        return {
            key: {
                "requests": self.requests[key],
                "input_tokens": self.input_tokens[key],
                "output_tokens": self.output_tokens[key],
                "cost_usd": round(self.cost_usd[key], 6),
            }
            for key in self.requests
        }
