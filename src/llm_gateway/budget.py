"""Per-client spend caps.

The policy reads accumulated spend from the CostTracker and decides
whether a client is over its cap. Enforcement is checked *before* a
request is routed: once a client's recorded spend reaches its cap, the
next request is blocked (hard) or flagged (soft). Clients without a
configured cap are uncapped.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BudgetPolicy:
    caps: dict[str, float]  # client key -> USD cap
    mode: str = "soft"      # "off" | "soft" | "hard"

    def status(self, client: str, spent: float) -> str:
        """'ok', 'over', or 'uncapped' for a client at a given spend level."""
        cap = self.caps.get(client)
        if cap is None:
            return "uncapped"
        return "over" if spent >= cap else "ok"

    def should_block(self, client: str, spent: float) -> bool:
        return self.mode == "hard" and self.status(client, spent) == "over"

    def remaining(self, client: str, spent: float) -> float | None:
        cap = self.caps.get(client)
        return None if cap is None else max(0.0, cap - spent)
