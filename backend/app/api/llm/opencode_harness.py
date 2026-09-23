"""OpenCode harness provider — calls a running opencode serve instance."""
import logging

import httpx

from app.api.llm.base import AbstractLLMProvider, LLMResult

logger = logging.getLogger(__name__)


class OpenCodeHarnessProvider(AbstractLLMProvider):
    """Sends messages to a headless opencode serve instance via its HTTP API.

    The serve instance handles all provider/model logic, auth, and tool use.
    Aurum only passes the user message and gets back the assistant reply.

    No native tool calling on our side (`supports_tools=False`): opencode
    works from a flattened prompt, so the ChatService uses the
    prompt-embedded JSON action protocol with this backend instead.
    """

    def __init__(self, base_url: str = "http://127.0.0.1:4096"):
        self.base_url = base_url.rstrip("/")

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> LLMResult:
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

            # 3. Extract text (and reasoning, when present) from the parts
            parts = data.get("parts", [])
            text_parts = [p["text"] for p in parts if p.get("type") == "text"]
            reasoning_parts = [
                p["text"] for p in parts
                if p.get("type") in ("reasoning", "thinking") and p.get("text")
            ]

            # 4. Clean up session (optional, keeps opencode tidy)
            try:
                await client.delete(f"{self.base_url}/session/{session_id}")
            except Exception:
                pass  # not critical

            return LLMResult(
                text="\n".join(text_parts),
                reasoning="\n".join(reasoning_parts) or None,
            )

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
            elif role == "tool":
                parts.append(f"[Tool result]\n{content}")
        return "\n\n".join(parts)
