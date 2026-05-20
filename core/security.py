"""Security helpers for the PR review service.

Currently provides
------------------
verify_github_signature(...)
    Verifies the ``X-Hub-Signature-256`` HMAC header GitHub adds to every
    webhook delivery, using the shared secret configured in your GitHub
    webhook settings. Uses constant-time comparison to prevent timing attacks.
"""

import hashlib
import hmac
import logging


logger = logging.getLogger(__name__)


def verify_github_signature(
    raw_body: bytes,
    signature_header: str | None,
    secret: str,
) -> bool:
    """Return True if the request signature matches the secret.

    Parameters
    ----------
    raw_body:
        The exact bytes of the HTTP request body. Must be raw (not re-serialized).
    signature_header:
        Value of the ``X-Hub-Signature-256`` header, e.g. ``"sha256=abc123..."``.
    secret:
        The webhook secret configured in GitHub *and* in your environment.
    """
    if not secret:
        # Caller is responsible for handling "no secret configured" mode.
        return False

    if not signature_header or not signature_header.startswith("sha256="):
        logger.warning("Missing or malformed X-Hub-Signature-256 header")
        return False

    received_sig = signature_header.split("=", 1)[1].strip()

    expected_sig = hmac.new(
        key=secret.encode("utf-8"),
        msg=raw_body,
        digestmod=hashlib.sha256,
    ).hexdigest()

    # Constant-time comparison to avoid timing side channels.
    return hmac.compare_digest(received_sig, expected_sig)

