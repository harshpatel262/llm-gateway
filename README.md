# LLM Gateway

[![CI](https://github.com/harshpatel262/llm-gateway/actions/workflows/ci.yml/badge.svg)](https://github.com/harshpatel262/llm-gateway/actions/workflows/ci.yml)

**One reliable API in front of every model provider.** A production-pattern gateway for teams running GenAI in production: smart routing with automatic failover, per-target circuit breakers, semantic response caching, per-client rate limits, and cost accounting — all observable through a single `/metrics` endpoint.

![Demo: routed completion, semantic cache hit, and live metrics](docs/demo.gif)

*(recorded with [VHS](https://github.com/charmbracelet/vhs) from [docs/demo.tape](docs/demo.tape) — reproducible against a mock-mode server)*

## Why

Once more than one team calls more than one model, every service ends up re-implementing the same plumbing: retries, provider outage handling, key management, cost attribution. A gateway centralizes that operational layer so application code makes one call and the platform team keeps control of reliability and spend.

## Architecture

```mermaid
flowchart LR
    C[Client services] -->|X-API-Key| A[Auth]
    A --> R[Rate limiter<br/>token bucket / client]
    R --> S[Semantic cache<br/>cosine similarity]
    S -->|miss| RT[Router]
    S -->|hit| C
    RT -->|primary| P1[Anthropic]
    RT -->|failover| P2[OpenAI]
    RT --> CB{{Circuit breakers<br/>per provider/model}}
    RT --> CT[Cost tracker] --> M[/metrics/]
```

**Request path:** authenticate → rate limit → cache lookup → route (retries + failover + circuit breaking) → record cost → cache store.

### Reliability model

- **Route aliases, not model ids.** Clients ask for `"default"` or `"fast"`; the platform decides which provider/model serves it. Models can be swapped fleet-wide without a single client change.
- **Ordered failover with retries.** Each route is an ordered target list. Transient failures retry with exponential backoff; persistent failures fail over to the next target.
- **Per-target circuit breakers.** A target that fails repeatedly gets its circuit opened and is skipped for a cooldown window, so a degraded provider can't add timeout latency to every request.
- **Semantic caching.** Prompts are embedded (hashing-trick BOW by default — deterministic, microsecond-fast, zero dependencies) and near-duplicate requests on the same route are served from cache. The embedder is a single pluggable function; swap in a real embedding model for stronger paraphrase recall.
- **Cost controls.** Every response is priced from a per-model table and attributed to the calling client key; `/metrics` exposes per-client spend, token usage, cache hit rates, and breaker states.
- **Budget caps.** Each client key can carry a spend cap. Enforcement is configurable: `off` (track only), `soft` (allow but flag over-budget clients via the `X-Budget-Status` response header), or `hard` (return `402 Payment Required` once a client is over its cap). The check runs before routing, so an over-budget client never incurs further spend.

## API

```bash
curl -s localhost:8000/v1/chat \
  -H 'X-API-Key: demo-key' \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "default",
    "messages": [{"role": "user", "content": "Summarize our refund policy"}]
  }'

# => {"text": "...", "provider": "anthropic", "model": "claude-sonnet-4-6",
#     "usage": {"input_tokens": 11, "output_tokens": 64}, "cached": false, "cost_usd": 0.000993}

curl -s localhost:8000/metrics -H 'X-API-Key: demo-key'
# => {"cache": {"hits": 3, "misses": 9},
#     "clients": {"demo-key": {"requests": 12, "cost_usd": 0.004113, ...}},
#     "budgets": {"mode": "soft",
#                 "clients": {"demo-key": {"cap_usd": 50.0, "spent_usd": 0.004113,
#                                          "remaining_usd": 49.995887, "status": "ok"}}},
#     "circuit_breakers": {"anthropic/claude-sonnet-4-6": {"open": false, ...}}}
```

## Quickstart

```bash
git clone https://github.com/harshpatel262/llm-gateway && cd llm-gateway
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# real providers (either or both; two providers enables cross-provider failover)
export GATEWAY_ANTHROPIC_API_KEY=sk-ant-...
export GATEWAY_OPENAI_API_KEY=sk-...
# or run fully offline against the mock provider
export GATEWAY_MOCK_MODE=true

uvicorn llm_gateway.main:app --reload
```

Tests run offline, no keys required:

```bash
pytest -v
```

## Configuration

| Variable | Default | Description |
|---|---|---|
| `GATEWAY_ANTHROPIC_API_KEY` / `GATEWAY_OPENAI_API_KEY` | — | Upstream provider keys |
| `GATEWAY_CLIENT_KEYS` | `{"demo-key": 60}` | JSON map of client API key → requests/minute |
| `GATEWAY_CACHE_TTL_SECONDS` | `300` | Semantic cache entry lifetime |
| `GATEWAY_CACHE_SIMILARITY_THRESHOLD` | `0.97` | Cosine similarity needed for a cache hit |
| `GATEWAY_BREAKER_FAILURE_THRESHOLD` | `3` | Consecutive failures before a target's circuit opens |
| `GATEWAY_BREAKER_COOLDOWN_SECONDS` | `30` | How long an open circuit skips its target |
| `GATEWAY_CLIENT_BUDGETS` | `{}` | JSON map of client API key → USD spend cap |
| `GATEWAY_BUDGET_ENFORCEMENT` | `soft` | `off`, `soft` (flag via header), or `hard` (402 over cap) |
| `GATEWAY_MOCK_MODE` | `false` | Route everything to the offline mock provider |

## Roadmap

- [ ] Streaming (SSE) pass-through with token-level cost metering
- [ ] Redis backends for cache and rate limits (multi-instance deployments)
- [x] Per-client budget caps with hard/soft enforcement
- [ ] Time-windowed budgets (monthly reset) backed by a durable store
- [ ] Prometheus exposition format for `/metrics`

## License

MIT
