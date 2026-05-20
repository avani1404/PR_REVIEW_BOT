"""GitHub authentication helpers.

Two auth modes are supported, in this preference order:

1) GitHub App (preferred for production)
   - Mint a short-lived JWT (RS256) signed with your App's private key.
   - Use that JWT to fetch a per-installation Access Token (~1h lifetime).
   - Cache the installation token until it nears expiry.

2) Personal Access Token (PAT)
   - Used as-is from settings if no App is configured.
   - Suitable for local dev only.

Public entry point
------------------
get_token_for_repo(owner, repo) -> (auth_scheme, token)
    Returns the value to use in the HTTP Authorization header:
        Authorization: <auth_scheme> <token>
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Optional, Tuple

import jwt  # PyJWT
import requests

from config.settings import get_settings


logger = logging.getLogger(__name__)

_settings = get_settings()

# Token cache:  installation_id -> {"token": str, "expires_at": epoch_seconds}
_token_cache: dict[int, dict] = {}
_cache_lock = threading.Lock()

# How early (seconds) to refresh a token before its declared expiry.
_REFRESH_SAFETY_WINDOW = 60


# ----------------------------------------------------------------------------
# Configuration helpers
# ----------------------------------------------------------------------------

def _load_private_key() -> Optional[str]:
    """Return the App's PEM private key from inline content or file path."""
    if _settings.github_app_private_key:
        return _settings.github_app_private_key
    if _settings.github_app_private_key_path:
        with open(_settings.github_app_private_key_path, "r", encoding="utf-8") as f:
            return f.read()
    return None


def is_app_configured() -> bool:
    """True if both an App ID and a private key are available."""
    return bool(_settings.github_app_id) and bool(_load_private_key())


# ----------------------------------------------------------------------------
# JWT minting
# ----------------------------------------------------------------------------

def generate_app_jwt() -> str:
    """Create a short-lived JWT proving 'I am this GitHub App'.

    GitHub allows a maximum lifetime of 10 minutes; we use ~9 minutes and
    set iat 60s in the past to tolerate small clock drift.
    """
    if not is_app_configured():
        raise RuntimeError("GitHub App is not configured (missing app id or private key)")

    private_key = _load_private_key()
    now = int(time.time())
    payload = {
        "iat": now - 60,            # tolerate up to 60s of clock skew
        "exp": now + (9 * 60),      # GitHub max is 10 min; stay safely under
        "iss": _settings.github_app_id,
    }
    return jwt.encode(payload, private_key, algorithm="RS256")


# ----------------------------------------------------------------------------
# Installation discovery + access tokens
# ----------------------------------------------------------------------------

def discover_installation_id(owner: str, repo: str) -> int:
    """Ask GitHub which installation has access to this repo."""
    app_jwt = generate_app_jwt()
    url = f"https://api.github.com/repos/{owner}/{repo}/installation"
    resp = requests.get(
        url,
        headers={
            "Authorization": f"Bearer {app_jwt}",
            "Accept": "application/vnd.github+json",
        },
        timeout=_settings.github_api_timeout,
    )
    resp.raise_for_status()
    return int(resp.json()["id"])


def _mint_installation_token(installation_id: int) -> dict:
    """Exchange an App JWT for a fresh installation access token."""
    app_jwt = generate_app_jwt()
    url = f"https://api.github.com/app/installations/{installation_id}/access_tokens"
    resp = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {app_jwt}",
            "Accept": "application/vnd.github+json",
        },
        timeout=_settings.github_api_timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    # Example expires_at: "2026-05-03T19:30:00Z"
    expires_at = int(
        datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00")).timestamp()
    )
    return {"token": data["token"], "expires_at": expires_at}


def get_installation_token(installation_id: int) -> str:
    """Cached accessor for installation tokens."""
    now = int(time.time())
    with _cache_lock:
        cached = _token_cache.get(installation_id)
        if cached and (cached["expires_at"] - now) > _REFRESH_SAFETY_WINDOW:
            return cached["token"]

    fresh = _mint_installation_token(installation_id)

    with _cache_lock:
        _token_cache[installation_id] = fresh
        logger.info(
            "Refreshed installation token for id=%s (expires at %s)",
            installation_id,
            datetime.fromtimestamp(fresh["expires_at"], tz=timezone.utc).isoformat(),
        )
    return fresh["token"]


# ----------------------------------------------------------------------------
# Public entry point
# ----------------------------------------------------------------------------

def get_token_for_repo(owner: str, repo: str) -> Tuple[str, str]:
    """Return ``(auth_scheme, token)`` to use in the Authorization header.

    Prefers GitHub App tokens when configured; otherwise falls back to PAT.
    Raises if neither is available.
    """
    if is_app_configured():
        installation_id = (
            _settings.github_app_installation_id
            or discover_installation_id(owner, repo)
        )
        token = get_installation_token(installation_id)
        return "Bearer", token

    if _settings.github_token:
        return "token", _settings.github_token

    raise RuntimeError(
        "No GitHub auth configured. Set GITHUB_APP_ID + GITHUB_APP_PRIVATE_KEY_PATH "
        "or GITHUB_TOKEN in your environment."
    )


