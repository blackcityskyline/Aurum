"""Generic OpenAI-compatible chat completions provider.

Works with any endpoint that follows the OpenAI /chat/completions format:
OpenRouter, OpenAI, Groq, Ollama, LM Studio, vLLM, and others.
Only base_url, api_key, and model are needed — no provider-specific code.
"""
import json
import logging

import httpx

from app.api.llm.base import AbstractLLMProvider

logger = logging.getLogger(__name__)


class OpenAICompatibleProvider(AbstractLLMProvider):
    def __init__(
        self,
        base_url: str,
        api_key: str = "",
        model: str = "",
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ):
        if not base_url:
            raise ValueError("llm_base_url is required for openai_compatible provider")
        if not model:
            raise ValueError("llm_model is required for openai_compatible provider")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> str:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload: dict = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }
        if tools:
            payload["tools"] = tools

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()

        choices = data.get("choices") or []
        if not choices:
            logger.warning("Empty choices in response: %s", json.dumps(data)[:500])
            return ""
        return choices[0].get("message", {}).get("content", "") or ""
