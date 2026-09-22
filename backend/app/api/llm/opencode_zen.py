"""OpenCode Zen provider — supports free and paid models via OpenAI-compatible API."""
import json

import httpx

from app.api.llm.base import AbstractLLMProvider
from app.core.config import Settings

BASE_URL = "https://opencode.ai/zen/v1"

# Free models available on Zen (no cost)
FREE_MODELS = [
    "big-pickle",
    "mimo-v2.6-flash-free",
    "mimo-v2.5-free",
    "ling-3.0-flash-fin-free",
    "nemotron-3-ultra-free",
    "nemotron-3.5-lightning-free",
]

DEFAULT_FREE_MODEL = "mimo-v2.5-free"


class OpenCodeZenProvider(AbstractLLMProvider):
    """OpenCode Zen — OpenAI-compatible chat completions endpoint."""

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> str:
        settings = Settings()
        model = settings.llm_model or DEFAULT_FREE_MODEL
        api_key = settings.llm_api_key

        if not api_key:
            return json.dumps({
                "reply": "OpenCode Zen API key not configured. Set AURUM_LLM_API_KEY.",
                "actions": [],
            })

        payload: dict = {
            "model": model,
            "messages": messages,
            "max_tokens": settings.llm_max_tokens,
            "temperature": settings.llm_temperature,
        }

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
