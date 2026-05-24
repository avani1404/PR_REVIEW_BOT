# PR Review Bot

An agentic AI system that automatically reviews GitHub Pull Requests and posts inline code comments directly on the diff. Built as a learning tutorial for multi-agent pipeline design.

---

## What It Does

When a PR is opened, updated, or reopened on GitHub, this bot:

1. Fetches the PR diff and HEAD commit from GitHub
2. Parses the diff into per-file chunks with line positions
3. Sends each file's diff to a local LLM for senior-level code review
4. Deduplicates redundant comments using semantic embeddings
5. Maps each AI comment back to the exact diff line using cosine similarity
6. Posts the comments as inline review comments directly on the PR

---

## Project Structure

```
pr_review_bot/
│
├── main.py                     # CLI entry point — manually trigger a review
├── webhook.py                  # Flask webhook server — triggered by GitHub events
├── requirements.txt
├── .env                        # Local secrets (gitignored)
├── .gitignore
├── README.md                   # ← You are here
│
├── orchestrator/
│   ├── __init__.py
│   └── orchestrator.py         # Wires agents into a sequential pipeline
│
├── agents/
│   ├── __init__.py
│   ├── base_agent.py           # Template method base: timing, logging, error handling
│   ├── fetch_agent.py          # Fetches diff + commit SHA from GitHub
│   ├── diff_parser_agent.py    # Splits diff into per-file structured data
│   ├── review_agent.py         # Sends diff to LLM, gets JSON review
│   ├── dedup_agent.py          # Removes semantically duplicate comments
│   ├── matching_agent.py       # Maps comments to exact diff lines
│   └── commenting_agent.py     # Posts inline comments to GitHub
│
├── core/
│   ├── __init__.py
│   ├── pr_context.py           # Shared pipeline data container (dataclass)
│   ├── github_api.py           # GitHub REST API calls with tenacity retries
│   ├── github_auth.py          # GitHub App JWT + PAT authentication
│   ├── diff_parser.py          # Diff splitting and position extraction (unidiff)
│   ├── llm_reviewer.py         # Ollama LLM prompt + call
│   ├── json_utils.py           # Robust JSON extractor for messy LLM output
│   ├── embedding_utils.py      # Ollama embeddings + cosine similarity
│   ├── deduplication.py        # Keyword + semantic dedup logic
│   ├── matching.py             # Embedding-based comment-to-line matching
│   ├── formatting.py           # Severity emoji formatting for comment bodies
│   ├── security.py             # HMAC-SHA256 webhook signature verification
│   └── utils.py                # PR URL parser + fuzzy string matching
│
├── config/
│   ├── __init__.py
│   ├── settings.py             # All env-driven settings in one frozen dataclass
│   └── logging_config.py       # One-time global logging setup
│
└── docs/
    ├── architecture.md         # System design, pipeline flow, data flow diagrams
    ├── agents.md               # Each agent: responsibility, inputs, outputs
    ├── core.md                 # Core module reference
    ├── config.md               # Configuration reference (all env vars)
    └── orchestrator.md         # Orchestrator design and pipeline wiring
```

---

## Quickstart

### Prerequisites

- Python 3.11+
- [Ollama](https://ollama.com) running locally with `llama3` and `nomic-embed-text` pulled
- A GitHub token (PAT) or GitHub App configured

### Installation

```bash
git clone https://github.com/your-org/pr-review-bot.git
cd pr-review-bot
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env          # fill in your secrets
```

### Environment Variables

Copy `.env.example` and fill in the values. At minimum you need either a GitHub PAT or a GitHub App configured. See [docs/config.md](docs/config.md) for the full reference.

```bash
# Minimal PAT setup
GITHUB_TOKEN=ghp_your_token_here
LLM_MODEL=llama3
EMBEDDING_MODEL=nomic-embed-text
```

### Run Manually (CLI)

```bash
python main.py
# Enter PR URL: https://github.com/owner/repo/pull/42
```

### Run as Webhook Server

```bash
python webhook.py
```

Then configure your GitHub repository webhook:
- **Payload URL**: `http://your-server:5001/webhook`
- **Content type**: `application/json`
- **Secret**: same value as `WEBHOOK_SECRET` in your `.env`
- **Events**: Pull requests

---

## Authentication

Two modes are supported, in preference order:

| Mode | When to use | How to configure |
|---|---|---|
| **GitHub App** | Production — scoped permissions, short-lived tokens | Set `GITHUB_APP_ID` + `GITHUB_APP_PRIVATE_KEY_PATH` |
| **Personal Access Token** | Local development | Set `GITHUB_TOKEN` |

See [docs/config.md](docs/config.md) for all available settings.

---

## How the Pipeline Works

```
GitHub Webhook / CLI
        │
        ▼
  OrchestratorAgent
        │
        ├──▶ FetchAgent          → populates commit_id, raw_diff
        ├──▶ DiffParserAgent     → populates parsed_files
        ├──▶ ReviewAgent         → populates reviews_by_file
        ├──▶ DeduplicationAgent  → populates deduped_reviews
        ├──▶ MatchingAgent       → populates mapped_comments
        └──▶ CommentingAgent     → posts comments to GitHub
```

All agents share a single `PRContext` dataclass that flows through the pipeline. Each agent reads what it needs, writes what it produces, and records its timing in `context.stats`.

For a detailed breakdown, see [docs/architecture.md](docs/architecture.md).

---

## Documentation

| File | Contents |
|---|---|
| [docs/architecture.md](docs/architecture.md) | End-to-end system design, data flow, and sequence diagrams |
| [docs/agents.md](docs/agents.md) | Each agent's responsibility, inputs, outputs, and design notes |
| [docs/core.md](docs/core.md) | Core module reference — GitHub API, embeddings, deduplication, matching |
| [docs/config.md](docs/config.md) | Full environment variable reference with defaults |
| [docs/orchestrator.md](docs/orchestrator.md) | Orchestrator design and how to extend the pipeline |

---

## Known Limitations & Roadmap

See [OPEN_NOTES.md](OPEN_NOTES.md) for the full deferred-work checklist. Key items:

- [ ] Migrate `Settings` dataclass to `pydantic-settings` for runtime validation
- [ ] Add Pydantic schemas for LLM output to reject malformed responses early
- [ ] Honor `Retry-After` header on HTTP 429 from GitHub
- [ ] Enforce webhook strict mode in production (`ENVIRONMENT=prod` + empty `WEBHOOK_SECRET` → refuse to start)
- [ ] Replace Ollama with Vertex AI once integration is finalized

---

## Tech Stack

| Layer | Library |
|---|---|
| HTTP / GitHub API | `requests`, `tenacity` |
| Webhook server | `Flask` |
| Diff parsing | `unidiff` |
| LLM inference | `ollama` (llama3) |
| Embeddings | `ollama` (nomic-embed-text) |
| Fuzzy matching | `rapidfuzz` |
| GitHub App auth | `PyJWT[crypto]` |
| Config | `python-dotenv` |
