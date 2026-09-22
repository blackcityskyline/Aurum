"""OpenCode harness provider — calls a running opencode serve instance."""
import json
import logging

import httpx

from app.api.llm.base import AbstractLLMProvider

logger = logging.getLogger(__name__)


class OpenCodeHarnessProvider(AbstractLLMProvider):
    """Sends messages to a headless opencode serve instance via its HTTP API.

    The serve instance handles all provider/model logic, auth, and tool use.
    Aurum only passes the user message and gets back the assistant reply.
    """

    def __init__(self, base_url: str = "http://127.0.0.1:4096"):
        self.base_url = base_url.rstrip("/")

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> str:
        # Build the user message text from the message history.
        # We send the full history as context, but opencode works with
        # individual prompts — so we flatten the conversation into one prompt.
        prompt = self._build_prompt(messages)

        # 1. Create a session
        async with httpx.AsyncClient(timeout=120) as client:
            session_resp = await client.post(
                f"{self.base_url}/session",
                json={},
            )
            session_resp.raise_for_status()
            session_id = session_resp.json()["id"]

            # 2. Send the message
            msg_resp = await client.post(
                f"{self.base_url}/session/{session_id}/message",
                json={
                    "parts": [{"type": "text", "text": prompt}],
                },
            )
            msg_resp.raise_for_status()
            data = msg_resp.json()

            # 3. Extract text from response parts
            parts = data.get("parts", [])
            text_parts = [p["text"] for p in parts if p.get("type") == "text"]
            reply = "\n".join(text_parts) if text_parts else ""

            # 4. Clean up session (optional, keeps opencode tidy)
            try:
                await client.delete(f"{self.base_url}/session/{session_id}")
            except Exception:
                pass  # not critical

            return reply

    def _build_prompt(self, messages: list[dict]) -> str:
        """Flatten message history into a single prompt for opencode.

        The system messages become context, user/assistant messages become
        the conversation history.
        """
        parts: list[str] = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                parts.append(f"[Context]\n{content}")
            elif role == "user":
                parts.append(f"User: {content}")
            elif role == "assistant":
                parts.append(f"Assistant: {content}")
        return "\n\n".join(parts)
