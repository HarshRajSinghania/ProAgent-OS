from __future__ import annotations

from typing import List

import httpx

from proagent_os.llm.base import LLMMessage, LLMProvider, LLMResponse


class OpenAICompatProvider(LLMProvider):
    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    async def chat(
        self,
        messages: List[LLMMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        payload = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        content = data["choices"][0]["message"]["content"]
        return LLMResponse(content=content, model=data.get("model", self.model), usage=data.get("usage", {}), raw=data)
