"""Centralized application settings.

Why this exists
---------------
All tunable knobs (env-driven values, model names, thresholds, timeouts)
should live in ONE place. Modules across the codebase then read from
``get_settings()`` instead of calling ``os.getenv`` or hard-coding values
themselves.

Benefits
--------
- One place to look when something needs tuning.
- One place to validate / document configuration.
- One place to swap providers (e.g., Vertex AI vs Ollama).
- Predictable defaults; easy environment overrides.
"""

import os
from dataclasses import dataclass, field
from functools import lru_cache

from dotenv import load_dotenv


# Load .env once at import time so any caller of get_settings() sees vars.
load_dotenv()


def _get_str(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value not in (None, "") else default


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw in (None, ""):
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _get_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw in (None, ""):
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw in (None, ""):
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    # ---- GitHub ----
    github_token: str = field(default_factory=lambda: _get_str("GITHUB_TOKEN", ""))
    github_api_timeout: int = field(default_factory=lambda: _get_int("GITHUB_API_TIMEOUT", 30))
    # Retry policy for transient GitHub failures (5xx, 429, network errors)
    github_max_retries: int = field(default_factory=lambda: _get_int("GITHUB_MAX_RETRIES", 5))
    github_retry_min_wait: float = field(default_factory=lambda: _get_float("GITHUB_RETRY_MIN_WAIT", 1.0))
    github_retry_max_wait: float = field(default_factory=lambda: _get_float("GITHUB_RETRY_MAX_WAIT", 10.0))

    # ---- GitHub App (preferred over PAT when configured) ----
    # Numeric App ID from https://github.com/settings/apps/<your-app>
    github_app_id: str = field(default_factory=lambda: _get_str("GITHUB_APP_ID", ""))
    # Path to the App's downloaded private-key .pem file.
    github_app_private_key_path: str = field(default_factory=lambda: _get_str("GITHUB_APP_PRIVATE_KEY_PATH", ""))
    # Optional: inline PEM contents (useful in containers/CI).
    github_app_private_key: str = field(default_factory=lambda: _get_str("GITHUB_APP_PRIVATE_KEY", ""))
    # Optional: explicit installation ID. If 0 / empty, we auto-discover per repo.
    github_app_installation_id: int = field(default_factory=lambda: _get_int("GITHUB_APP_INSTALLATION_ID", 0))

    # ---- LLM (review) ----
    llm_model: str = field(default_factory=lambda: _get_str("LLM_MODEL", "llama3"))

    # ---- Embeddings ----
    embedding_model: str = field(default_factory=lambda: _get_str("EMBEDDING_MODEL", "nomic-embed-text"))
    embedding_cache_size: int = field(default_factory=lambda: _get_int("EMBEDDING_CACHE_SIZE", 2048))

    # ---- Pipeline thresholds ----
    dedup_threshold: float = field(default_factory=lambda: _get_float("DEDUP_THRESHOLD", 0.80))
    match_threshold: float = field(default_factory=lambda: _get_float("MATCH_THRESHOLD", 0.75))

    # ---- Webhook server ----
    webhook_host: str = field(default_factory=lambda: _get_str("WEBHOOK_HOST", "0.0.0.0"))
    webhook_port: int = field(default_factory=lambda: _get_int("WEBHOOK_PORT", 5001))
    webhook_debug: bool = field(default_factory=lambda: _get_bool("WEBHOOK_DEBUG", True))

    # Shared secret used by GitHub to sign webhook payloads (HMAC-SHA-256).
    # Set this in .env to enable signature verification. If empty, the server
    # will accept unsigned requests (dev mode) and log a clear warning.
    webhook_secret: str = field(default_factory=lambda: _get_str("WEBHOOK_SECRET", ""))

    # ---- Logging ----
    log_level: str = field(default_factory=lambda: _get_str("LOG_LEVEL", "INFO"))
    log_format: str = field(
        default_factory=lambda: _get_str(
            "LOG_FORMAT",
            "%(asctime)s %(levelname)s [%(name)s] %(message)s",
        )
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached, process-wide Settings instance."""
    return Settings()

