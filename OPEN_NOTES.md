# Open Notes / Future Polish

A running checklist of small but meaningful improvements we deliberately deferred
during the phased build-out of the PR Review microservices project. Pick from
this list once the main phases (0 → 4) are done.

Status legend: `[ ]` open · `[~]` partially done · `[x]` done

---

## From Phase 1 — Quick Wins
- [x] Add a single centralized logging config module (done in `config/logging_config.py`).
- [ ] Audit remaining `print(` matches inside prompt/example text in `core/llm_reviewer.py` and `core/json_utils.py`. They are *not* runtime console prints, but worth a comment or constant.

## From Phase 2 — Architecture
### Subtask A — `PRContext`
- [ ] Tighten guards: `context.raw_diff` could be `None` if GitHub fetch fails. Today we default to `""` in `DiffParserAgent._run()`. Make this an explicit error or a typed empty diff.
- [ ] Once no external code calls `agent.execute(...)`, remove the legacy `execute(...)` methods entirely (also clears related lint warnings).

### Subtask B — `FetchAgent`
- [x] FetchAgent is the natural place for retries → done in Phase 3 Subtask B.
- [x] FetchAgent is the natural place for GitHub App auth → handled in Phase 3 Subtask C.

### Subtask C — Centralized config (`config/settings.py`)
- [ ] Migrate the dataclass-based `Settings` to `pydantic-settings` for runtime validation, ranges, and clearer error messages on misconfig.
- [ ] Add a documented `.env.example` enumerating every supported env var.

### Subtask D — `BaseAgent` template method
- [ ] Drop legacy `execute(...)` methods after migration is fully complete.
- [ ] Add a final pipeline summary log line in the orchestrator iterating `context.stats` (per-agent elapsed_ms / status).
- [ ] Forward `context.stats` to a metrics backend (Prometheus / Datadog / CloudWatch) when observability stack is added.

## From Phase 3 — Security & Robustness
### Subtask A — Webhook signature validation
- [ ] Enforce strict mode (refuse to start if `WEBHOOK_SECRET` is empty and `ENVIRONMENT=prod`) once an `ENVIRONMENT` setting is introduced.
- [ ] Pass through GitHub `X-GitHub-Delivery` / our own request-id into log records for end-to-end traceability when async workers arrive.

### Subtask B — `tenacity` retries on GitHub API
- [ ] Honor `Retry-After` header on HTTP 429 responses instead of relying purely on exponential backoff.
- [ ] Apply the same retry pattern to LLM and embedding calls once they hit a real networked provider (Vertex AI / OpenAI / etc.).

### Subtask C — GitHub App migration (this is the active work)
- [ ] Add a small CLI helper (`python -m tools.app_status`) that prints which auth mode is active (App vs PAT) and (if App) the installation ID and token expiry. Useful for ops debugging.
- [ ] Document key-rotation procedure for the GitHub App private key.

### Subtask D — Pydantic models for LLM output
- [ ] (To be planned) — define strict Pydantic schemas for review entries and reject malformed LLM output early.

## From Phase 0 housekeeping
- [ ] Remove `ollama` from `requirements.txt` once Vertex AI integration is finalized (already flagged in the requirements file).

---

## How to use this list
1. After Phase 4 production work is complete, walk this list top-to-bottom.
2. Convert each item into a small dedicated PR/branch.
3. Tick items in this file as they're shipped.

