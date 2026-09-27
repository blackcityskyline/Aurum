"""Pydantic schemas for the chat AI's backend configuration (Settings →
AI). API keys are write-only: reads never return the stored key, only
`has_api_key`, so the value can't leak through the API/UI once saved."""
from typing import Literal

from pydantic import BaseModel, Field


class LlmProviderRead(BaseModel):
    id: int
    name: str
    base_url: str
    model: str | None
    has_api_key: bool
    is_active: bool = False


class LlmProviderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    base_url: str = Field(min_length=1, max_length=300, pattern=r"^https?://")
    # Optional — local endpoints (Ollama/vLLM) legitimately have no key.
    api_key: str | None = Field(default=None, max_length=500)
    model: str | None = Field(default=None, max_length=200)
    # Make this the active provider right away (frontend's default for
    # the first/only provider).
    activate: bool = True


class LlmProviderUpdate(BaseModel):
    """Partial update. `api_key` semantics: omitted → unchanged, empty
    string or null → cleared, non-empty → replaced."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    base_url: str | None = Field(default=None, min_length=1, max_length=300, pattern=r"^https?://")
    api_key: str | None = Field(default=None, max_length=500)
    model: str | None = Field(default=None, max_length=200)
    activate: bool | None = None


class LlmSettingsRead(BaseModel):
    mode: Literal["harness", "api", "stub"]
    harness_type: str
    harness_url: str
    harness_model: str | None
    max_tokens: int
    temperature: float
    active_provider_id: int | None
    providers: list[LlmProviderRead]


class LlmSettingsUpdate(BaseModel):
    mode: Literal["harness", "api"] | None = None
    harness_type: str | None = Field(default=None, min_length=1, max_length=30)
    harness_url: str | None = Field(default=None, min_length=1, max_length=300, pattern=r"^https?://")
    # Opaque driver-side id ("opencode/big-pickle"); "" or null → clear
    # the pin and fall back to the harness's own default model.
    harness_model: str | None = Field(default=None, max_length=200)
    max_tokens: int | None = Field(default=None, ge=256, le=32768)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    active_provider_id: int | None = None


class LlmModelsRequest(BaseModel):
    """Fetch the model catalogue from an OpenAI-compatible /models endpoint.
    Works with unsaved form values (base_url/api_key straight from the UI),
    which is the point: the model picker must offer real ids *before* the
    provider row is committed.

    `base_url` is optional because a saved row can answer on its own — the
    chat's model picker sends just `provider_id`. Which of the two must be
    present is a cross-field rule, so it's enforced in the route rather than
    here (either way a request with neither gets a 400, never a 500)."""

    base_url: str | None = Field(default=None, max_length=300)
    api_key: str | None = Field(default=None, max_length=500)
    provider_id: int | None = None  # fill base_url/api_key from a saved row


class LlmModelsResponse(BaseModel):
    models: list[str]


class HarnessModelRead(BaseModel):
    """Generic harness model row (base.HarnessModel) — `id` is opaque and
    driver-specific, everything else is display-only."""

    id: str
    label: str
    provider: str
    context: int | None = None
    tool_calling: bool = False


class HarnessModelsResponse(BaseModel):
    models: list[HarnessModelRead]


class LlmTestResponse(BaseModel):
    ok: bool
    detail: str
