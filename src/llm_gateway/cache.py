"""Semantic response cache.

Prompts are embedded with a hashing-trick bag-of-words vector — fully
deterministic, dependency-free, and computed in microseconds. Lookups
return a cached response when cosine similarity to a previous prompt on
the same route crosses the threshold. The embedder is intentionally
pluggable: swap `embed` for a real embedding model to trade lookup cost
for better paraphrase recall.
"""

from __future__ import annotations

import hashlib
import math
import re
import time
from collections import OrderedDict
from dataclasses import dataclass

from llm_gateway.providers.base import ChatResponse

_DIM = 256
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def embed(text: str) -> list[float]:
    vector = [0.0] * _DIM
    for token in _TOKEN_RE.findall(text.lower()):
        digest = hashlib.md5(token.encode()).digest()
        index = int.from_bytes(digest[:4], "little") % _DIM
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += sign
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


@dataclass
class _Entry:
    vector: list[float]
    route: str
    response: ChatResponse
    expires_at: float


class SemanticCache:
    def __init__(self, ttl_seconds: int = 300, threshold: float = 0.97, max_entries: int = 1024):
        self._ttl = ttl_seconds
        self._threshold = threshold
        self._max_entries = max_entries
        self._entries: OrderedDict[str, _Entry] = OrderedDict()
        self.hits = 0
        self.misses = 0

    @staticmethod
    def _prompt_text(messages: list) -> str:
        return "\n".join(f"{m.role}:{m.content}" for m in messages)

    def get(self, route: str, messages: list) -> ChatResponse | None:
        now = time.monotonic()
        for key in [k for k, e in self._entries.items() if e.expires_at <= now]:
            del self._entries[key]

        query = embed(self._prompt_text(messages))
        best: _Entry | None = None
        best_score = self._threshold
        for entry in self._entries.values():
            if entry.route != route:
                continue
            score = cosine(query, entry.vector)
            if score >= best_score:
                best, best_score = entry, score

        if best is None:
            self.misses += 1
            return None
        self.hits += 1
        return best.response.model_copy(update={"cached": True})

    def put(self, route: str, messages: list, response: ChatResponse) -> None:
        text = self._prompt_text(messages)
        key = f"{route}:{hashlib.md5(text.encode()).hexdigest()}"
        self._entries[key] = _Entry(
            vector=embed(text),
            route=route,
            response=response,
            expires_at=time.monotonic() + self._ttl,
        )
        self._entries.move_to_end(key)
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)
