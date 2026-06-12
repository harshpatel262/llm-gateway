from __future__ import annotations

import httpx

from llm_gateway.providers.base import (
    ChatRequest,
    ChatResponse,
    Provider,
    ProviderError,
    Usage,
)

API_URL = "https://api.openai.com/v1/chat/completions"


class OpenAIProvider(Provider):
    name = "openai"

    def __init__(self, api_key: str, timeout: float = 60.0):
        self._api_key = api_key
        self._timeout = timeout

    async def complete(self, request: ChatRequest, model: str) -> ChatResponse:
        payload = {
            "model": model,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    API_URL,
                    json=payload,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProviderError(f"openai: {exc}") from exc

        body = response.json()
        return ChatResponse(
            text=body["choices"][0]["message"]["content"] or "",
            provider=self.name,
            model=model,
            usage=Usage(
                input_tokens=body.get("usage", {}).get("prompt_tokens", 0),
                output_tokens=body.get("usage", {}).get("completion_tokens", 0),
            ),
        )
