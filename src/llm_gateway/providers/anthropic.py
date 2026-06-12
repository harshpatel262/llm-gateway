from __future__ import annotations

import httpx

from llm_gateway.providers.base import (
    ChatRequest,
    ChatResponse,
    Provider,
    ProviderError,
    Usage,
)

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"


class AnthropicProvider(Provider):
    name = "anthropic"

    def __init__(self, api_key: str, timeout: float = 60.0):
        self._api_key = api_key
        self._timeout = timeout

    async def complete(self, request: ChatRequest, model: str) -> ChatResponse:
        system_parts = [m.content for m in request.messages if m.role == "system"]
        messages = [
            {"role": m.role, "content": m.content}
            for m in request.messages
            if m.role != "system"
        ]
        payload: dict = {
            "model": model,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "messages": messages,
        }
        if system_parts:
            payload["system"] = "\n".join(system_parts)

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    API_URL,
                    json=payload,
                    headers={
                        "x-api-key": self._api_key,
                        "anthropic-version": API_VERSION,
                    },
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProviderError(f"anthropic: {exc}") from exc

        body = response.json()
        return ChatResponse(
            text="".join(
                block["text"] for block in body.get("content", []) if block.get("type") == "text"
            ),
            provider=self.name,
            model=model,
            usage=Usage(
                input_tokens=body.get("usage", {}).get("input_tokens", 0),
                output_tokens=body.get("usage", {}).get("output_tokens", 0),
            ),
        )
