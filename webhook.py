from flask import Flask, request
import threading
import json
import logging
from config.logging_config import configure_logging
from config.settings import get_settings
from core.security import verify_github_signature

from orchestrator.orchestrator import OrchestratorAgent

# python3 -c "import secrets; print(secrets.token_hex(32))"
# paste this secret in webook secret in git
# WEBHOOK_SECRET=<paste-the-same-value> in .env file


app = Flask(__name__)
configure_logging()
logger = logging.getLogger(__name__)
settings = get_settings()

if not settings.webhook_secret:
    logger.warning(
        "WEBHOOK_SECRET is not set — webhook signature verification is DISABLED. "
        "Do not run this configuration in production."
    )


def run_async_review(pr_url):
    try:
        orchestrator = OrchestratorAgent()
        orchestrator.run(pr_url)
    except Exception:
        logger.exception("Background job failed for PR: %s", pr_url)


@app.route("/webhook", methods=["POST"])
def github_webhook():

    logger.info("Webhook received")

    event = request.headers.get("X-GitHub-Event")
    signature = request.headers.get("X-Hub-Signature-256")
    raw_body = request.get_data(cache=True)  # raw bytes, used for HMAC

    if settings.webhook_secret:
        if not verify_github_signature(raw_body, signature, settings.webhook_secret):
            logger.warning("Rejected webhook: invalid or missing signature")
            return "Unauthorized", 401

    try:
        payload = json.loads(raw_body.decode("utf-8")) if raw_body else None
    except json.JSONDecodeError:
        logger.warning("Rejected webhook: body is not valid JSON")
        return "Bad Request", 400

    logger.info("Event: %s", event)

    if not payload:
        logger.warning("No payload in webhook request")
        return "Bad Request", 400

    if event == "pull_request":

        action = payload.get("action")
        logger.info("Action: %s", action)

        if action in ["opened", "synchronize", "reopened"]:

            pr_url = payload["pull_request"]["html_url"]

            logger.info("Queueing review for: %s", pr_url)

            thread = threading.Thread(target=run_async_review, args=(pr_url,))
            thread.start()

    return "OK", 200


if __name__ == "__main__":
    app.run(
        host=settings.webhook_host,
        port=settings.webhook_port,
        debug=settings.webhook_debug,
    )
