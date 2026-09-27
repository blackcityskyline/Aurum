"""Stub LLM provider — echoes input for testing without an API key."""
import json

from app.api.llm.base import AbstractLLMProvider, LLMResult


class StubProvider(AbstractLLMProvider):
    """Returns a canned response that mimics what a real LLM would produce.

    Useful for:
    - Testing the full chat pipeline without network calls
    - Frontend development before a real provider is configured
    - Debugging the context-building logic
    """

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> LLMResult:
        last_user_msg = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                last_user_msg = msg.get("content", "")
                break

        reply = (
            f"[Stub AI] Received your message ({len(last_user_msg)} chars). "
            "No LLM backend is configured — open Settings → AI and pick the "
            "harness or an API provider."
        )

        action = {
            "type": "info",
            "params": {"raw_message": last_user_msg},
            "status": "simulated",
        }
        return LLMResult(
            text=json.dumps({"reply": reply, "actions": [action]}),
            reasoning="[stub] no reasoning — this backend just echoes.",
        )
