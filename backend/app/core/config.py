"""Application configuration, sourced from environment variables (.env)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

# Single source of truth for the running app's version — surfaced in the API
# title, /api/health (which the frontend reads to show it in Settings), and
# embedded in exported backups so an old file can be told apart from a
# current one.
APP_VERSION = "1.1.5"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="AURUM_", extra="ignore")

    # Postgres connection
    postgres_user: str = "aurum"
    postgres_password: str = "aurum"
    postgres_db: str = "aurum"
    postgres_host: str = "db"
    postgres_port: int = 5432

    # Default currency shown across the UI when an account doesn't override it
    default_currency: str = "USD"

    # Comma-separated list of browser origins allowed to call the API. Empty
    # by default, which allows none: the shipped compose serves the UI and the
    # API from one nginx, and the Vite dev server proxies /api, so neither is
    # a cross-origin caller. Set it only for a genuinely separate frontend.
    cors_origins: str = ""

    # CoinGecko Demo API key (free, no card required — https://www.coingecko.com/en/api/pricing)
    # for services/crypto_service.py's price lookups. Empty by default; the
    # Crypto tab's endpoints 400 with a clear message until this is set,
    # rather than silently hitting CoinGecko's much stingier keyless tier.
    coingecko_api_key: str = ""

    # Chat / AI agent
    # Providers:
    #   stub             — echo, no LLM
    #   opencode         — headless opencode serve harness (recommended)
    #   openai_compatible — any OpenAI-compatible API (OpenRouter, OpenAI,
    #                        Groq, Ollama, vLLM, ...)
    llm_provider: str = "opencode"
    opencode_url: str = "http://127.0.0.1:4096"
    # openai_compatible settings (ignored when llm_provider != openai_compatible)
    llm_base_url: str = ""      # e.g. https://openrouter.ai/api/v1
    llm_api_key: str = ""
    llm_model: str = ""         # e.g. openrouter/auto, meta-llama/llama-3.1-8b-instruct:free
    llm_max_tokens: int = 2048
    llm_temperature: float = 0.7

    # Directory for file uploads (chat attachments, etc.)
    upload_dir: str = "/tmp/aurum_uploads"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def cors_origins_list(self) -> list[str]:
        if self.cors_origins == "*":
            return ["*"]
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
