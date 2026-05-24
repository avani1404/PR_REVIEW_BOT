# Architecture

This document describes the end-to-end design of the PR Review Bot — how a GitHub webhook becomes a set of inline code review comments.

---

## Table of Contents

- [High-Level Overview](#high-level-overview)
- [Pipeline Flow Diagram](#pipeline-flow-diagram)
- [PRContext — The Shared Data Container](#prcontext--the-shared-data-container)
- [Data Flow Through the Pipeline](#data-flow-through-the-pipeline)
- [Sequence Diagram — Webhook to Posted Comment](#sequence-diagram--webhook-to-posted-comment)
- [Authentication Flow](#authentication-flow)
- [Embedding Pipeline](#embedding-pipeline)
- [Design Principles](#design-principles)

---

## High-Level Overview

The system is a **sequential multi-agent pipeline**. A single shared data container (`PRContext`) is passed from agent to agent. Each agent has one clear responsibility: it reads specific fields from the context, does its work, and writes its results back.

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Entry Points                                │
│                                                                     │
│   ┌─────────────┐                    ┌──────────────────────────┐   │
│   │   main.py   │  ← CLI / manual    │       webhook.py         │   │
│   │  (input PR  │                    │  (Flask HTTP server)     │   │
│   │    URL)     │                    │  listens on :5001        │   │
│   └──────┬──────┘                    └────────────┬─────────────┘   │
│          │                                        │                 │
│          └──────────────────┬─────────────────────┘                 │
│                             │                                       │
│                             ▼                                       │
│                    OrchestratorAgent                                │
│               (wires pipeline, passes PRContext)                    │
└─────────────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────▼───────────────┐
              │         Agent Pipeline         │
              │                               │
              │  1. FetchAgent                │
              │  2. DiffParserAgent           │
              │  3. ReviewAgent               │
              │  4. DeduplicationAgent        │
              │  5. MatchingAgent             │
              │  6. CommentingAgent           │
              └───────────────────────────────┘
```

---

## Pipeline Flow Diagram

Each stage transforms the `PRContext`. Arrows show what each agent **reads** (←) and **writes** (→).

```
                        ┌──────────────────────────────────────────┐
                        │              PRContext                   │
                        │  pr_url, owner, repo, pr_number          │
                        └────────────────────┬─────────────────────┘
                                             │
                          ┌──────────────────▼──────────────────┐
                          │           FetchAgent                │
                          │                                     │
                          │  Reads:   owner, repo, pr_number    │
                          │  Calls:   GitHub REST API           │
                          │  Writes:  commit_id                 │
                          │           raw_diff (full diff text) │
                          └──────────────────┬──────────────────┘
                                             │
                          ┌──────────────────▼──────────────────┐
                          │         DiffParserAgent             │
                          │                                     │
                          │  Reads:   raw_diff                  │
                          │  Parses:  per-file diffs via        │
                          │           unidiff + custom splitter │
                          │  Writes:  parsed_files              │
                          │    {filename: {raw_diff,            │
                          │               diff_data: [          │
                          │                 {file, line_content,│
                          │                  line_number,       │
                          │                  position}]}}       │
                          └──────────────────┬──────────────────┘
                                             │
                          ┌──────────────────▼──────────────────┐
                          │           ReviewAgent               │
                          │                                     │
                          │  Reads:   parsed_files              │
                          │  Calls:   Ollama LLM (llama3)       │
                          │           once per file             │
                          │  Writes:  reviews_by_file           │
                          │    {filename: [                     │
                          │      {line_content, comment,        │
                          │       severity, suggestion}]}       │
                          └──────────────────┬──────────────────┘
                                             │
                          ┌──────────────────▼──────────────────┐
                          │        DeduplicationAgent           │
                          │                                     │
                          │  Reads:   reviews_by_file           │
                          │  Uses:    keyword matching +        │
                          │           nomic-embed-text          │
                          │           cosine similarity         │
                          │  Writes:  deduped_reviews           │
                          │    (same shape, fewer entries)      │
                          └──────────────────┬──────────────────┘
                                             │
                          ┌──────────────────▼──────────────────┐
                          │          MatchingAgent              │
                          │                                     │
                          │  Reads:   parsed_files              │
                          │           deduped_reviews           │
                          │  Uses:    embeddings on both        │
                          │           review lines + diff lines │
                          │           cosine similarity         │
                          │           match_threshold (0.75)    │
                          │  Writes:  mapped_comments           │
                          │    [{path, line, body}]             │
                          └──────────────────┬──────────────────┘
                                             │
                          ┌──────────────────▼──────────────────┐
                          │         CommentingAgent             │
                          │                                     │
                          │  Reads:   mapped_comments           │
                          │           commit_id                 │
                          │           owner, repo, pr_number    │
                          │  Calls:   GitHub REST API           │
                          │           POST /pulls/:id/comments  │
                          │  Result:  inline comments on PR ✓   │
                          └─────────────────────────────────────┘
```

---

## PRContext — The Shared Data Container

`PRContext` is a Python `dataclass` defined in `core/pr_context.py`. It is the **single source of truth** for all data moving through the pipeline. No agent passes data directly to another — everything is mediated through this object.

```
┌─────────────────────────────────────────────────────────────────────┐
│                          PRContext                                  │
├──────────────────────┬──────────────────────────────────────────────┤
│ FIELD                │ SET BY              │ TYPE                   │
├──────────────────────┼─────────────────────┼────────────────────────┤
│ pr_url               │ Orchestrator        │ str                    │
│ owner                │ Orchestrator        │ str                    │
│ repo                 │ Orchestrator        │ str                    │
│ pr_number            │ Orchestrator        │ str                    │
├──────────────────────┼─────────────────────┼────────────────────────┤
│ commit_id            │ FetchAgent          │ Optional[str]          │
│ raw_diff             │ FetchAgent          │ Optional[str]          │
├──────────────────────┼─────────────────────┼────────────────────────┤
│ parsed_files         │ DiffParserAgent     │ Dict[str, Any]         │
│ reviews_by_file      │ ReviewAgent         │ Dict[str, List[Dict]]  │
│ deduped_reviews      │ DeduplicationAgent  │ Dict[str, List[Dict]]  │
│ mapped_comments      │ MatchingAgent       │ List[Dict]             │
├──────────────────────┼─────────────────────┼────────────────────────┤
│ stats                │ BaseAgent.run()     │ Dict[str, Dict]        │
│                      │ (every agent)       │ {agent: {elapsed_ms,   │
│                      │                     │  status, error}}       │
└──────────────────────┴─────────────────────┴────────────────────────┘
```

**Why a dataclass instead of passing arguments between agents?**

- Any agent can read any earlier result without the orchestrator needing to know what each agent needs
- Adding a new field (e.g., `reviewer_config`) requires changing only `PRContext`, not every agent signature
- `stats` gives free per-agent observability without any agent needing to instrument itself

---

## Data Flow Through the Pipeline

This diagram shows how data is shaped and transformed at each stage, from raw GitHub API response to a structured comment posted on the PR.

```
GitHub API response (raw diff text)
         │
         │   "diff --git a/core/utils.py b/core/utils.py\n
         │    index abc..def 100644\n
         │    --- a/core/utils.py\n
         │    +++ b/core/utils.py\n
         │    @@ -1,3 +1,8 @@\n
         │    +from rapidfuzz import fuzz\n
         │    +def parse_pr_url(pr_url): ..."
         │
         ▼  DiffParserAgent splits by file, extracts positions
         │
{
  "core/utils.py": {
    "raw_diff": "...",
    "diff_data": [
      {
        "file": "core/utils.py",
        "line_content": "from rapidfuzz import fuzz",
        "line_number": 1,           ← actual file line number
        "position": 1               ← position within diff hunk
      },
      ...
    ]
  }
}
         │
         ▼  ReviewAgent sends raw_diff per file to Ollama LLM
         │
{
  "core/utils.py": [
    {
      "line_content": "from rapidfuzz import fuzz",
      "comment": "Consider adding a version pin comment for rapidfuzz",
      "severity": "low",
      "suggestion": "from rapidfuzz import fuzz  # rapidfuzz>=3.9"
    },
    ...
  ]
}
         │
         ▼  DeduplicationAgent removes near-duplicate comments
         │  (keyword check first, then cosine similarity on embeddings)
         │
{
  "core/utils.py": [
    { ...unique comments only... }
  ]
}
         │
         ▼  MatchingAgent embeds each AI comment line + each diff line,
         │  finds best cosine match above threshold (0.75)
         │
[
  {
    "path": "core/utils.py",
    "line": 1,
    "body": "🟢 **LOW**: Consider adding a version pin...\n\n```suggestion\nfrom rapidfuzz import fuzz  # rapidfuzz>=3.9\n```"
  },
  ...
]
         │
         ▼  CommentingAgent POSTs each item to GitHub API
         │
GitHub PR ← inline comment appears on line 1 of core/utils.py ✓
```

---

## Sequence Diagram — Webhook to Posted Comment

```
GitHub          webhook.py       OrchestratorAgent    FetchAgent    GitHub API    Ollama
  │                 │                    │                 │              │           │
  │  POST /webhook  │                    │                 │              │           │
  │────────────────▶│                    │                 │              │           │
  │                 │ verify HMAC sig    │                 │              │           │
  │                 │ parse payload      │                 │              │           │
  │                 │ extract pr_url     │                 │              │           │
  │                 │                    │                 │              │           │
  │                 │ thread.start()     │                 │              │           │
  │  200 OK ◀───────│                    │                 │              │           │
  │                 │                    │                 │              │           │
  │                 │ orchestrator.run() │                 │              │           │
  │                 │───────────────────▶│                 │              │           │
  │                 │                    │ agent.run()     │              │           │
  │                 │                    │────────────────▶│              │           │
  │                 │                    │                 │ GET /pulls/N │           │
  │                 │                    │                 │─────────────▶│           │
  │                 │                    │                 │ commit_id    │           │
  │                 │                    │                 │◀─────────────│           │
  │                 │                    │                 │ GET diff     │           │
  │                 │                    │                 │─────────────▶│           │
  │                 │                    │                 │ raw_diff     │           │
  │                 │                    │                 │◀─────────────│           │
  │                 │                    │ PRContext ◀─────│              │           │
  │                 │                    │                 │              │           │
  │                 │              [DiffParserAgent]       │              │           │
  │                 │              [parses diff locally]   │              │           │
  │                 │                    │                 │              │           │
  │                 │              [ReviewAgent]           │              │           │
  │                 │                    │                 │              │  prompt   │
  │                 │                    │─────────────────────────────────────────▶ │
  │                 │                    │                 │              │  JSON     │
  │                 │                    │ ◀───────────────────────────────────────  │
  │                 │                    │                 │              │           │
  │                 │              [DeduplicationAgent]    │              │           │
  │                 │              [MatchingAgent]         │              │           │
  │                 │              [both use Ollama        │              │           │
  │                 │               embeddings locally]    │              │           │
  │                 │                    │                 │              │           │
  │                 │              [CommentingAgent]       │              │           │
  │                 │                    │  POST comment   │              │           │
  │                 │                    │─────────────────────────────▶ │           │
  │                 │                    │                 │  201 OK      │           │
  │                 │                    │ ◀───────────────────────────  │           │
  │                 │                    │                 │              │           │
```

---

## Authentication Flow

The bot supports two GitHub auth modes. `github_auth.py` selects the best available option automatically.

```
get_token_for_repo(owner, repo)
          │
          ├── Is GITHUB_APP_ID set AND private key available?
          │         │
          │        YES
          │         │
          │         ▼
          │   Is GITHUB_APP_INSTALLATION_ID set?
          │     │               │
          │    YES              NO
          │     │               │
          │     │               ▼
          │     │    discover_installation_id(owner, repo)
          │     │    → GET /repos/{owner}/{repo}/installation
          │     │    → returns installation_id
          │     │               │
          │     └───────────────┘
          │               │
          │               ▼
          │   get_installation_token(installation_id)
          │     │
          │     ├── Token in cache AND not near expiry (<60s)?
          │     │         → return cached token
          │     │
          │     └── Otherwise:
          │             generate_app_jwt()
          │               → RS256 JWT signed with private key
          │               → iat = now-60s (clock skew tolerance)
          │               → exp = now+9min
          │             POST /app/installations/{id}/access_tokens
          │               → returns token + expires_at
          │             cache token
          │               → return token
          │
          └── Is GITHUB_TOKEN set?
                    │
                   YES → return ("token", GITHUB_TOKEN)
                    │
                   NO  → raise RuntimeError (no auth configured)
```

Token caching is thread-safe via `threading.Lock()`. Tokens are proactively refreshed 60 seconds before expiry to prevent mid-request expirations.

---

## Embedding Pipeline

Deduplication and line matching both rely on text embeddings. The embedding pipeline is shared and cached.

```
         Input text (comment or diff line)
                      │
                      ▼
         get_embedding(text)
                      │
                      ▼
         Normalize whitespace
         " ".join(text.split())
                      │
                      ▼
         Empty after normalization?
              │              │
             YES             NO
              │              │
              ▼              ▼
         return []    _get_embedding_cached(text)
                             │
                    ┌────────┴────────────┐
                    │   LRU cache hit?    │
                    │  (maxsize from      │
                    │   settings)         │
                    └────────┬────────────┘
                        │         │
                      HIT        MISS
                        │         │
                        │         ▼
                        │   ollama.embeddings(
                        │     model="nomic-embed-text",
                        │     prompt=text
                        │   )
                        │         │
                        └────┬────┘
                             │
                             ▼
                    embedding vector (list[float])
                             │
                             ▼
              cosine_similarity(vec1, vec2)
                             │
              ┌──────────────┴──────────────┐
              │  Deduplication              │  Matching
              │  sim > dedup_threshold?     │  Find highest sim
              │  (default 0.80)             │  across all diff lines
              │  YES → skip comment         │  sim >= match_threshold?
              │  NO  → keep comment         │  (default 0.75)
              └─────────────────────────────┘  NO → discard
                                               YES → map to line
```

The LRU cache is applied at import time using the `embedding_cache_size` setting (default 2048). This means identical lines in a large diff (e.g., repeated import statements) are only embedded once per process lifetime.

---

## Design Principles

**1. Single-responsibility agents**
Each agent does exactly one thing. `FetchAgent` only talks to GitHub. `ReviewAgent` only calls the LLM. This makes each stage independently testable and replaceable.

**2. PRContext as the pipeline contract**
Agents never call each other directly. The orchestrator passes the context object; agents read and write fields. Adding a new pipeline stage means adding a new dataclass field and a new agent — nothing else changes.

**3. BaseAgent as the template method**
`BaseAgent.run()` handles timing, logging, and exception recording uniformly for every agent. Individual agents only implement `_run()`. This means observability is free — every agent's elapsed time and status are recorded in `context.stats` without any agent needing to write that code.

**4. All config in one place**
`config/settings.py` is the single source of truth for every tunable value. No module calls `os.getenv()` directly. This makes it easy to audit what can be configured, and the frozen dataclass prevents accidental mutation at runtime.

**5. Fail-fast on auth, retry on transient errors**
`tenacity` retries on network errors and HTTP 5xx/429. It does not retry on 4xx errors (bad request, not found, unauthorized) — those represent logic errors that retrying cannot fix, so they raise immediately.
