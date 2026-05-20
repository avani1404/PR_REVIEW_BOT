import logging

import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)

from config.settings import get_settings
from core.github_auth import get_token_for_repo


settings = get_settings()
HTTP_TIMEOUT = settings.github_api_timeout

logger = logging.getLogger(__name__)


# HTTP status codes that are worth retrying (transient).
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class TransientGitHubError(Exception):
    """Raised for transient GitHub failures that tenacity should retry."""


class GitHubAPIError(Exception):
    """Raised for non-retryable GitHub failures (4xx other than 429)."""


def _build_headers(owner: str, repo: str, accept: str) -> dict:
    """Resolve auth (App or PAT) and build standard request headers."""
    scheme, token = get_token_for_repo(owner, repo)
    return {
        "Authorization": f"{scheme} {token}",
        "Accept": accept,
    }


@retry(
    reraise=True,
    stop=stop_after_attempt(settings.github_max_retries),
    wait=wait_exponential(
        multiplier=1,
        min=settings.github_retry_min_wait,
        max=settings.github_retry_max_wait,
    ),
    retry=retry_if_exception_type(
        (TransientGitHubError, requests.exceptions.ConnectionError, requests.exceptions.Timeout)
    ),
    before_sleep=before_sleep_log(logger, logging.WARNING),
)
def _request_with_retry(method: str, url: str, *, headers: dict, json_body: dict | None = None) -> requests.Response:
    """Single retry-aware HTTP call to GitHub.

    Retries on:
        - Network errors (ConnectionError, Timeout)
        - HTTP 429 / 5xx responses (TransientGitHubError)

    Does NOT retry on logical errors (4xx other than 429); those raise
    GitHubAPIError immediately so the caller can fail fast.
    """
    response = requests.request(
        method=method,
        url=url,
        headers=headers,
        json=json_body,
        timeout=HTTP_TIMEOUT,
    )

    if response.status_code in _RETRYABLE_STATUS:
        raise TransientGitHubError(
            f"Transient GitHub error {response.status_code}: {response.text[:200]}"
        )

    if not response.ok:
        raise GitHubAPIError(
            f"GitHub API error {response.status_code}: {response.text[:200]}"
        )

    return response


def get_pr_head_commit(owner, repo, pr_number):
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
    headers = _build_headers(owner, repo, "application/vnd.github.v3+json")
    response = _request_with_retry("GET", url, headers=headers)
    return response.json()["head"]["sha"]


def get_pr_diff(owner, repo, pr_number):
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
    headers = _build_headers(owner, repo, "application/vnd.github.v3.diff")
    response = _request_with_retry("GET", url, headers=headers)
    return response.text


def post_inline_comments(owner, repo, pr_number, comments, commit_id):
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/comments"
    headers = _build_headers(owner, repo, "application/vnd.github.v3+json")

    for comment in comments:
        data = {
            "path": comment["path"],              # file path
            "line": int(comment["line"]),         # 🔥 exact line
            "side": "RIGHT",                      # required
            "body": comment["body"],              # comment text
            "commit_id": commit_id                # 🔥 CRITICAL FIX
        }
        try:
            _request_with_retry("POST", url, headers=headers, json_body=data)
            logger.info("Comment posted on line %s", comment["line"])
        except (TransientGitHubError, GitHubAPIError) as exc:
            # Don't fail the whole batch if one comment fails.
            logger.error("Failed to post inline comment on line %s: %s", comment["line"], exc)
