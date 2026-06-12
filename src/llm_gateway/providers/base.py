from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant" | "system"
    content: str


class ChatRequest(BaseModel):
    model: str = "default"  # a gateway route alias, not a provider model id
    messages: list[ChatMessage] = Field(min_length=1)
    max_tokens: int = 1024
    temperature: float = 0.7


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0


class ChatResponse(BaseModel):
    text: str
    provider: str
    model: str
    usage: Usage = Usage()
    cached: bool = False
    cost_usd: float = 0.0


class ProviderError(Exception):
    """Raised by providers on any upstream failure; the router treats every
    instance as a failover signal."""


class Provider(ABC):
    name: str

    @abstractmethod
    async def complete(self, request: ChatRequest, model: str) -> ChatResponse:
        """Execute a chat completion against a concrete provider model."""
