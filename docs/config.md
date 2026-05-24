# Configuration Reference

All runtime configuration is managed through `config/settings.py`. Every value can be overridden via environment variables or a `.env` file in the project root.

---

## Table of Contents

- [How Configuration Works](#how-configuration-works)
- [GitHub API](#github-api)
- [GitHub App Authentication](#github-app-authentication)
- [LLM — Review Model](#llm--review-model)
- [Embeddings](#embeddings)
- [Pipeline Thresholds](#pipeline-thresholds)
- [Webhook Server](#webhook-server)
- [Logging](#logging)
- [Quick Reference Table](#quick-reference-table)
- [Minimal .env Examples](#minimal-env-examples)

---

## How Configuration Works

`config/settings.py` defines a frozen `Settings` dataclass. All fields use `default_factory` lambdas that read from the environment at instantiation time. The `get_settings()` function is decorated with `@lru_cache(maxsize=1)`, so the settings object is created once and reused everywhere.

```
.env file (loaded once at import via python-dotenv)
       │
       ▼
  os.environ
       │
       ▼
  Settings.__init__()   ← called once by get_settings()
  (each field reads its env var, falls back to default)
       │
       ▼
  get_settings() → cached Settings instance
       │
       ▼
  Modules call get_settings() and read fields
  (never call os.getenv() directly)
```

**Type coercion helpers** in `settings.py` handle edge cases:

- `_get_str(name, default)` — treats empty string the same as missing (returns default)
- `_get_int(name, default)` — silently falls back to default on `ValueError`
- `_get_float(name, default)` — same as `_get_int`
- `_get_bool(name, default)` — truthy values: `"1"`, `"true"`, `"yes"`, `"on"` (case-insensitive)

---

## GitHub API

Settings for HTTP timeout and the tenacity retry policy used by `core/github_api.py`.

### GITHUB\_API\_TIMEOUT

| Property | Value |
|---|---|
| Type | int (seconds) |
| Default | `30` |
| Used in | `core/github_api.py`, `core/github_auth.py` |

Timeout in seconds for every outbound HTTP request to the GitHub API. Applies to both connection establishment and response reading.

```
GITHUB_API_TIMEOUT=30
```

### GITHUB\_MAX\_RETRIES

| Property | Value |
|---|---|
| Type | int |
| Default | `5` |
| Used in | `core/github_api.py` (tenacity `stop_after_attempt`) |

Maximum number of attempts for a single GitHub API call. This includes the initial attempt — 5 means 1 try + 4 retries.

```
GITHUB_MAX_RETRIES=5
```

### GITHUB\_RETRY\_MIN\_WAIT

| Property | Value |
|---|---|
| Type | float (seconds) |
| Default | `1.0` |
| Used in | `core/github_api.py` (tenacity `wait_exponential min`) |

Minimum wait time between retry attempts. The first retry will wait at least this long.

```
GITHUB_RETRY_MIN_WAIT=1.0
```

### GITHUB\_RETRY\_MAX\_WAIT

| Property | Value |
|---|---|
| Type | float (seconds) |
| Default | `10.0` |
| Used in | `core/github_api.py` (tenacity `wait_exponential max`) |

Maximum wait time between retry attempts. Exponential backoff is capped at this value to prevent excessively long waits.

```
GITHUB_RETRY_MAX_WAIT=10.0
```

---

## GitHub App Authentication

If these settings are configured, the bot authenticates as a GitHub App (recommended for production). If not, it falls back to `GITHUB_TOKEN`.

See [architecture.md — Authentication Flow](architecture.md#authentication-flow) for how these interact.

### GITHUB\_TOKEN

| Property | Value |
|---|---|
| Type | str |
| Default | `""` (empty — must be set for PAT mode) |
| Used in | `core/github_auth.py` |

A GitHub Personal Access Token (PAT) with `repo` scope. Used when GitHub App settings are not configured. Suitable for local development only.

```
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### GITHUB\_APP\_ID

| Property | Value |
|---|---|
| Type | str |
| Default | `""` |
| Used in | `core/github_auth.py` |

The numeric App ID from your GitHub App's settings page (`https://github.com/settings/apps/<your-app>`). Required for App authentication.

```
GITHUB_APP_ID=123456
```

### GITHUB\_APP\_PRIVATE\_KEY\_PATH

| Property | Value |
|---|---|
| Type | str (file path) |
| Default | `""` |
| Used in | `core/github_auth.py` |

Path to the `.pem` private key file downloaded from your GitHub App's settings. Either this or `GITHUB_APP_PRIVATE_KEY` must be set for App authentication.

```
GITHUB_APP_PRIVATE_KEY_PATH=/app/secrets/private-key.pem
```

### GITHUB\_APP\_PRIVATE\_KEY

| Property | Value |
|---|---|
| Type | str (PEM content) |
| Default | `""` |
| Used in | `core/github_auth.py` |

Inline PEM private key content. Useful in containerized deployments or CI where writing files is impractical. Takes precedence over `GITHUB_APP_PRIVATE_KEY_PATH` if both are set.

```
GITHUB_APP_PRIVATE_KEY=-----BEGIN RSA PRIVATE KEY-----\nMIIE...\n-----END RSA PRIVATE KEY-----
```

### GITHUB\_APP\_INSTALLATION\_ID

| Property | Value |
|---|---|
| Type | int |
| Default | `0` |
| Used in | `core/github_auth.py` |

Optional. The installation ID for the GitHub App on the target organization or account. If `0` or not set, the bot auto-discovers the installation ID by calling `GET /repos/{owner}/{repo}/installation`. Set this explicitly to avoid the discovery API call on every startup.

```
GITHUB_APP_INSTALLATION_ID=987654
```

---

## LLM — Review Model

### LLM\_MODEL

| Property | Value |
|---|---|
| Type | str |
| Default | `"llama3"` |
| Used in | `core/llm_reviewer.py` |

The Ollama model name to use for code review. The model must be pulled locally (`ollama pull llama3`). Any Ollama-compatible model name can be used here.

```
LLM_MODEL=llama3
# or
LLM_MODEL=codellama
# or
LLM_MODEL=mistral
```

---

## Embeddings

### EMBEDDING\_MODEL

| Property | Value |
|---|---|
| Type | str |
| Default | `"nomic-embed-text"` |
| Used in | `core/embedding_utils.py` |

The Ollama embedding model name. Used for both deduplication (comparing comment similarity) and matching (mapping comments to diff lines). Must be pulled locally (`ollama pull nomic-embed-text`).

```
EMBEDDING_MODEL=nomic-embed-text
```

### EMBEDDING\_CACHE\_SIZE

| Property | Value |
|---|---|
| Type | int |
| Default | `2048` |
| Used in | `core/embedding_utils.py` |

LRU cache size for embeddings. Identical strings (e.g., repeated `return None` lines across many files) are embedded only once and the result is cached. Increase this for large repositories with many repeated code patterns. Decrease it to reduce memory usage.

```
EMBEDDING_CACHE_SIZE=2048
```

---

## Pipeline Thresholds

These thresholds control the strictness of the deduplication and matching stages.

### DEDUP\_THRESHOLD

| Property | Value |
|---|---|
| Type | float (0.0 – 1.0) |
| Default | `0.80` |
| Used in | `core/deduplication.py` |

Cosine similarity threshold for the deduplication stage. Two comments with similarity above this value are considered duplicates — the second one is discarded.

```
┌──────────────────────────────────────────────────┐
│  Higher value (e.g., 0.95)                       │
│    → Only near-identical comments are removed    │
│    → More comments reach GitHub (noisier review) │
│                                                  │
│  Lower value (e.g., 0.60)                        │
│    → Aggressively removes related comments       │
│    → Fewer but broader-coverage comments         │
└──────────────────────────────────────────────────┘
```

```
DEDUP_THRESHOLD=0.80
```

### MATCH\_THRESHOLD

| Property | Value |
|---|---|
| Type | float (0.0 – 1.0) |
| Default | `0.75` |
| Used in | `core/matching.py` |

Cosine similarity threshold for the matching stage. A comment is only posted if its best-matching diff line has similarity at or above this value. Comments below the threshold are discarded (logged as "low-confidence match").

```
┌──────────────────────────────────────────────────┐
│  Higher value (e.g., 0.90)                       │
│    → Only very confident matches are posted      │
│    → Fewer comments, but correctly placed        │
│                                                  │
│  Lower value (e.g., 0.50)                        │
│    → More comments reach GitHub                  │
│    → Risk of comments placed on wrong lines      │
└──────────────────────────────────────────────────┘
```

```
MATCH_THRESHOLD=0.75
```

---

## Webhook Server

Settings for the Flask webhook server in `webhook.py`.

### WEBHOOK\_HOST

| Property | Value |
|---|---|
| Type | str |
| Default | `"0.0.0.0"` |
| Used in | `webhook.py` |

The host address Flask binds to. `0.0.0.0` listens on all interfaces. Set to `127.0.0.1` to accept only local connections.

```
WEBHOOK_HOST=0.0.0.0
```

### WEBHOOK\_PORT

| Property | Value |
|---|---|
| Type | int |
| Default | `5001` |
| Used in | `webhook.py` |

The port Flask listens on. Configure your GitHub webhook to send to this port.

```
WEBHOOK_PORT=5001
```

### WEBHOOK\_DEBUG

| Property | Value |
|---|---|
| Type | bool |
| Default | `true` |
| Used in | `webhook.py` |

Flask debug mode. **Must be set to `false` in production.** Debug mode enables the interactive debugger and auto-reloader, which are unsafe in production environments.

```
WEBHOOK_DEBUG=false
```

### WEBHOOK\_SECRET

| Property | Value |
|---|---|
| Type | str |
| Default | `""` (empty — dev mode) |
| Used in | `webhook.py`, `core/security.py` |

The HMAC-SHA256 shared secret used to verify GitHub webhook signatures. Must match the "Secret" field configured in your GitHub repository webhook settings.

Generate a strong secret:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

If empty, the webhook server accepts all requests and logs a warning. This is acceptable for local development but **must never be used in production**.

```
WEBHOOK_SECRET=your_64_character_hex_secret_here
```

---

## Logging

### LOG\_LEVEL

| Property | Value |
|---|---|
| Type | str |
| Default | `"INFO"` |
| Used in | `config/logging_config.py` |

Python logging level. Valid values: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`. `DEBUG` produces detailed per-line matching logs and is useful during development.

```
LOG_LEVEL=INFO
```

### LOG\_FORMAT

| Property | Value |
|---|---|
| Type | str |
| Default | `"%(asctime)s %(levelname)s [%(name)s] %(message)s"` |
| Used in | `config/logging_config.py` |

Python `logging.basicConfig` format string. The default includes timestamp, level, logger name (which is the agent or module name), and message.

```
LOG_FORMAT=%(asctime)s %(levelname)s [%(name)s] %(message)s
```

---

## Quick Reference Table

| Variable | Type | Default | Description |
|---|---|---|---|
| `GITHUB_TOKEN` | str | `""` | PAT for dev mode auth |
| `GITHUB_API_TIMEOUT` | int | `30` | HTTP timeout in seconds |
| `GITHUB_MAX_RETRIES` | int | `5` | Max tenacity retry attempts |
| `GITHUB_RETRY_MIN_WAIT` | float | `1.0` | Min backoff wait (seconds) |
| `GITHUB_RETRY_MAX_WAIT` | float | `10.0` | Max backoff wait (seconds) |
| `GITHUB_APP_ID` | str | `""` | GitHub App numeric ID |
| `GITHUB_APP_PRIVATE_KEY_PATH` | str | `""` | Path to App private key .pem |
| `GITHUB_APP_PRIVATE_KEY` | str | `""` | Inline PEM key content |
| `GITHUB_APP_INSTALLATION_ID` | int | `0` | App installation ID (0 = auto-discover) |
| `LLM_MODEL` | str | `"llama3"` | Ollama review model name |
| `EMBEDDING_MODEL` | str | `"nomic-embed-text"` | Ollama embedding model name |
| `EMBEDDING_CACHE_SIZE` | int | `2048` | LRU cache size for embeddings |
| `DEDUP_THRESHOLD` | float | `0.80` | Similarity threshold for deduplication |
| `MATCH_THRESHOLD` | float | `0.75` | Similarity threshold for line matching |
| `WEBHOOK_HOST` | str | `"0.0.0.0"` | Flask bind address |
| `WEBHOOK_PORT` | int | `5001` | Flask listen port |
| `WEBHOOK_DEBUG` | bool | `true` | Flask debug mode (disable in prod) |
| `WEBHOOK_SECRET` | str | `""` | HMAC secret for webhook verification |
| `LOG_LEVEL` | str | `"INFO"` | Python log level |
| `LOG_FORMAT` | str | (see above) | Python log format string |

---

## Minimal .env Examples

### Local development with PAT

```dotenv
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
LLM_MODEL=llama3
EMBEDDING_MODEL=nomic-embed-text
LOG_LEVEL=DEBUG
WEBHOOK_DEBUG=true
```

### Production with GitHub App

```dotenv
# GitHub App authentication
GITHUB_APP_ID=123456
GITHUB_APP_PRIVATE_KEY_PATH=/run/secrets/github-app-key.pem
GITHUB_APP_INSTALLATION_ID=987654

# Webhook security
WEBHOOK_SECRET=your_64_character_hex_secret_here
WEBHOOK_DEBUG=false
WEBHOOK_HOST=0.0.0.0
WEBHOOK_PORT=5001

# Models
LLM_MODEL=llama3
EMBEDDING_MODEL=nomic-embed-text

# Pipeline tuning
DEDUP_THRESHOLD=0.80
MATCH_THRESHOLD=0.75

# Logging
LOG_LEVEL=INFO
```
