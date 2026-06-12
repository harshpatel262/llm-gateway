from llm_gateway.cache import SemanticCache, cosine, embed
from llm_gateway.providers.base import ChatMessage, ChatResponse


def _messages(text: str) -> list[ChatMessage]:
    return [ChatMessage(role="user", content=text)]


def _response(text: str = "answer") -> ChatResponse:
    return ChatResponse(text=text, provider="mock", model="mock-large")


def test_identical_prompt_hits():
    cache = SemanticCache()
    cache.put("default", _messages("What is our refund policy?"), _response())

    hit = cache.get("default", _messages("What is our refund policy?"))
    assert hit is not None
    assert hit.cached is True


def test_near_duplicate_prompt_hits():
    cache = SemanticCache(threshold=0.90)
    cache.put(
        "default",
        _messages("What is our refund policy for enterprise customers in the US region?"),
        _response(),
    )
    hit = cache.get(
        "default",
        _messages("What is our refund policy for enterprise customers in the US region"),
    )
    assert hit is not None


def test_different_prompt_misses():
    cache = SemanticCache()
    cache.put("default", _messages("What is our refund policy?"), _response())
    assert cache.get("default", _messages("Summarize the Q3 earnings call")) is None
    assert cache.misses == 1


def test_routes_are_isolated():
    cache = SemanticCache()
    cache.put("default", _messages("same prompt"), _response())
    assert cache.get("fast", _messages("same prompt")) is None


def test_expired_entries_are_evicted():
    cache = SemanticCache(ttl_seconds=0)
    cache.put("default", _messages("ephemeral"), _response())
    assert cache.get("default", _messages("ephemeral")) is None


def test_capacity_evicts_oldest():
    cache = SemanticCache(max_entries=2)
    cache.put("default", _messages("first unique prompt"), _response())
    cache.put("default", _messages("second unique prompt"), _response())
    cache.put("default", _messages("third unique prompt"), _response())
    assert cache.get("default", _messages("first unique prompt")) is None
    assert cache.get("default", _messages("third unique prompt")) is not None


def test_embedding_similarity_ordering():
    a = embed("refund policy for enterprise customers")
    b = embed("refund policy for enterprise clients")
    c = embed("kubernetes pod scheduling internals")
    assert cosine(a, b) > cosine(a, c)
