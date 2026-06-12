"""Per-client token-bucket rate limiting."""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class _Bucket:
    capacity: float
    tokens: float
    refill_per_second: float
    updated_at: float


@dataclass
class RateLimiter:
    # requests/minute per client key; burst capacity equals one minute's quota
    limits: dict[str, int]
    _buckets: dict[str, _Bucket] = field(default_factory=dict)

    def allow(self, client_key: str) -> bool:
        rpm = self.limits.get(client_key)
        if rpm is None:
            return False

        now = time.monotonic()
        bucket = self._buckets.get(client_key)
        if bucket is None:
            bucket = _Bucket(
                capacity=float(rpm),
                tokens=float(rpm),
                refill_per_second=rpm / 60.0,
                updated_at=now,
            )
            self._buckets[client_key] = bucket

        elapsed = now - bucket.updated_at
        bucket.tokens = min(bucket.capacity, bucket.tokens + elapsed * bucket.refill_per_second)
        bucket.updated_at = now

        if bucket.tokens < 1.0:
            return False
        bucket.tokens -= 1.0
        return True
