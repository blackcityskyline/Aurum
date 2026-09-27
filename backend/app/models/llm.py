"""LLM configuration for the chat AI — deliberately its own two tables
rather than columns on app_settings: `app_settings` is exported/imported
as part of a backup (see services/backup_service.py), and API keys must
never end up inside a backup file a user might share around.

- LlmSettings: singleton row (id=1) — which *backend* serves the chat
  (harness = headless opencode serve, api = any OpenAI-compatible HTTP
  API, stub = canned echo for tests/dev) and its connection/generation
  parameters.
- LlmProvider: one row per configured API endpoint (OpenRouter, OpenAI,
  Groq, a local Ollama, ...). The settings row points at the active one.
  Multiple providers are stored so the UI can offer "pick any provider,
  any model" without losing the others.
"""
from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class LlmProvider(Base, TimestampMixin):
    __tablename__ = "llm_providers"

    id: Mapped[int] = mapped_column(primary_key=True)
    # UI label, e.g. "OpenRouter" — free-form, the user names it.
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # OpenAI-compatible root, e.g. https://openrouter.ai/api/v1
    base_url: Mapped[str] = mapped_column(String(300), nullable=False)
    # Sent as `Authorization: Bearer …`. Nullable: some local endpoints
    # (Ollama, vLLM) don't need one.
    api_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Chosen model id, e.g. meta-llama/llama-3.3-70b-instruct:free.
    # Stored per provider because model ids are provider-specific.
    model: Mapped[str | None] = mapped_column(String(200), nullable=True)


class LlmSettings(Base):
    """Singleton row (id=1) — same get-or-create pattern as AppSettings."""

    __tablename__ = "llm_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    # harness | api | stub. "stub" is only reachable via env seeding or a
    # direct PATCH — the UI offers just the two real modes.
    mode: Mapped[str] = mapped_column(String(20), nullable=False, default="harness")
    # Where the opencode serve instance listens (harness mode only).
    harness_url: Mapped[str] = mapped_column(
        String(300), nullable=False, default="http://host.docker.internal:4096"
    )
    # Which harness *driver* answers (key into api/llm/registry.HARNESSES).
    # Stored, not hardcoded, so a second harness is a drop-in module + a
    # registry line — no migration, no UI changes.
    harness_type: Mapped[str] = mapped_column(String(30), nullable=False, default="opencode")
    # Model pinned inside that harness — opaque driver-side id
    # ("opencode/big-pickle"); NULL = the harness's own default.
    harness_model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Which LlmProvider row is in use for api mode.
    active_provider_id: Mapped[int | None] = mapped_column(
        ForeignKey("llm_providers.id", ondelete="SET NULL"), nullable=True
    )
    # Generation parameters (api mode; harness mode keeps its own tuning
    # opencode-side — only the model is chosen here).
    max_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=2048)
    temperature: Mapped[float] = mapped_column(Float, nullable=False, default=0.7)
