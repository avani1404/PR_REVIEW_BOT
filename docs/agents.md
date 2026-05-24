# Agents

All agents live in the `agents/` package. Each one extends `BaseAgent` and implements a single `_run(context: PRContext) -> PRContext` method.

---

## Table of Contents

- [BaseAgent — The Template](#baseagent--the-template)
- [FetchAgent](#fetchagent)
- [DiffParserAgent](#diffparseragent)
- [ReviewAgent](#reviewagent)
- [DeduplicationAgent](#deduplicationagent)
- [MatchingAgent](#matchingagent)
- [CommentingAgent](#commentingagent)
- [Adding a New Agent](#adding-a-new-agent)

---

## BaseAgent — The Template

**File:** `agents/base_agent.py`

`BaseAgent` is not a pipeline stage — it is the foundation every agent builds on. It implements the [Template Method pattern](https://refactoring.guru/design-patterns/template-method): the `run()` method is fixed, and subclasses only supply `_run()`.

### What `run()` provides automatically

```
agent.run(context)
        │
        ├── log: "{AgentName} started"
        ├── start timer (time.perf_counter)
        │
        ├── call self._run(context)   ← subclass implements this
        │
        ├── (on exception)
        │     status = "error"
        │     error  = repr(exc)
        │     re-raise
        │
        └── finally (always runs):
              elapsed_ms = measured wall time
              context.stats[self.name] = {
                "elapsed_ms": elapsed_ms,
                "status":     "ok" | "error",
                "error":      None | repr(exc)
              }
              log: "{AgentName} finished in {N} ms (status=ok|error)"
```

### Why this matters

Every agent gets timing, structured logging, and error recording for free. No agent needs to write any of that boilerplate. The `context.stats` dict at the end of the pipeline gives a complete per-stage execution summary — useful for dashboards and debugging without any extra instrumentation.

### Legacy `execute()` method

Some agents still have an `execute(...)` method from before the `PRContext` migration. This is intentional: it is kept for backward compatibility while the migration is in progress. Once all callers use `_run()`, `execute()` will be removed. See [OPEN_NOTES.md](../OPEN_NOTES.md).

---

## FetchAgent

**File:** `agents/fetch_agent.py`

### Responsibility

The first stage in the pipeline. Talks to GitHub and populates the context with everything downstream agents need to do their work: the HEAD commit SHA and the full unified diff.

### Reads from context

| Field | Type | Source |
|---|---|---|
| `owner` | str | Orchestrator (from PR URL) |
| `repo` | str | Orchestrator (from PR URL) |
| `pr_number` | str | Orchestrator (from PR URL) |

### Writes to context

| Field | Type | Description |
|---|---|---|
| `commit_id` | str | HEAD commit SHA of the PR branch |
| `raw_diff` | str | Full unified diff text of the PR |

### How it works

```
FetchAgent._run(context)
        │
        ├── get_pr_head_commit(owner, repo, pr_number)
        │     → GET https://api.github.com/repos/{owner}/{repo}/pulls/{number}
        │     → returns response["head"]["sha"]
        │
        └── get_pr_diff(owner, repo, pr_number)
              → GET same URL with Accept: application/vnd.github.v3.diff
              → returns raw diff text
```

Both calls go through `_request_with_retry()` in `core/github_api.py`, which handles tenacity retries, auth header injection, and error classification. FetchAgent itself contains no retry or auth logic.

### Failure behavior

If GitHub returns a non-retryable 4xx, `GitHubAPIError` is raised and propagates up through `BaseAgent.run()`, which records `status="error"` and re-raises. The pipeline stops.

---

## DiffParserAgent

**File:** `agents/diff_parser_agent.py`

### Responsibility

Takes the raw unified diff text and transforms it into a structured, per-file data structure that later agents can work with. Extracts both the raw diff content per file and the specific added lines with their exact line numbers and diff positions.

### Reads from context

| Field | Type |
|---|---|
| `raw_diff` | Optional[str] |

Note: if `raw_diff` is `None` (e.g., GitHub fetch failed silently), the agent defaults to parsing an empty string. A future improvement will make this an explicit error. See [OPEN_NOTES.md](../OPEN_NOTES.md).

### Writes to context

| Field | Type | Shape |
|---|---|---|
| `parsed_files` | Dict[str, Any] | `{filename: {"raw_diff": str, "diff_data": [...]}}` |

Each entry in `diff_data` is:

```python
{
    "file":         "path/to/file.py",   # file path from diff header
    "line_content": "normalized line",   # added line, whitespace-normalized
    "line_number":  42,                  # actual line number in the file
    "position":     3                    # position within the diff hunk
}
```

### How it works

```
DiffParserAgent._run(context)
        │
        ├── split_diff_by_file(raw_diff)
        │     Scans for "diff --git" headers to split the monolithic
        │     diff into one chunk per file.
        │
        └── for each file:
              extract_diff_with_positions(file_diff)
                │
                ├── clean_diff()
                │     Remove: "new file mode", "deleted file mode",
                │             "index ..." lines
                │     These cause unidiff to fail.
                │
                ├── PatchSet(cleaned_diff)   ← unidiff library
                │
                └── for each file → hunk → line:
                      position += 1           (every line, not just added)
                      if line.is_added:
                        collect {file, line_content, line_number, position}
```

The `position` counter increments for **every** line in the hunk (added, removed, context), not just added lines. This is required by the GitHub API: it uses the diff position to place inline comments, not the file line number.

---

## ReviewAgent

**File:** `agents/review_agent.py`

### Responsibility

Sends each file's diff to the LLM and collects structured JSON review feedback. One LLM call is made per file in the PR diff.

### Reads from context

| Field | Type |
|---|---|
| `parsed_files` | Dict[str, Any] |

### Writes to context

| Field | Type | Shape |
|---|---|---|
| `reviews_by_file` | Dict[str, List[Dict]] | `{filename: [{line_content, comment, severity, suggestion}]}` |

### How it works

```
ReviewAgent._run(context)
        │
        └── for each file in parsed_files:
              │
              ├── review_file(file_name, raw_diff)
              │     → builds a strict prompt instructing the LLM to:
              │       - return valid JSON only
              │       - match line_content exactly to added lines
              │       - flag code quality, security, style, etc.
              │     → calls ollama.chat(model=llm_model, messages=[...])
              │     → returns raw string response from LLM
              │
              └── extract_json_from_text(response)
                    → robust JSON extractor that handles:
                      - comment stripping (// and #)
                      - print() quote escaping
                      - array boundary detection
                      - object-by-object fallback parsing
                    → returns list of review dicts
```

### Review object shape

```python
{
    "line_content": "if user == None:",        # EXACT added line from diff
    "comment":      "Use 'is None' instead",   # human-readable issue
    "severity":     "medium",                  # low | medium | high
    "suggestion":   "if user is None:"         # corrected code (optional)
}
```

### Why one call per file?

Sending the full diff of all files in one prompt would risk exceeding context limits for large PRs, and makes it harder for the LLM to keep `line_content` accurate. Per-file calls keep the context focused and the prompt manageable.

---

## DeduplicationAgent

**File:** `agents/dedup_agent.py`

### Responsibility

Removes near-duplicate review comments before they reach the matching and posting stages. A PR with many similar issues (e.g., multiple `print()` calls) would otherwise produce many near-identical comments cluttering the review.

### Reads from context

| Field | Type |
|---|---|
| `reviews_by_file` | Dict[str, List[Dict]] |

### Writes to context

| Field | Type | Shape |
|---|---|---|
| `deduped_reviews` | Dict[str, List[Dict]] | Same shape as input, fewer entries |

### How it works

Two-stage deduplication runs per file, in order:

```
for each comment in reviews_by_file[file]:

  Stage 1 — Keyword Check (fast, no embedding needed)
  ─────────────────────────────────────────────────────
  Extract topic keywords from the comment text:
    "print" | "logging" | "logger"  →  keyword: "logging"
    "variable" | "name"             →  keyword: "naming"
    "none"                          →  keyword: "none_check"
    "performance" | "optimize"      →  keyword: "performance"

  If ANY keyword overlaps with a previously-kept comment → SKIP
  (This catches obvious duplicates without the cost of an embedding call)

  Stage 2 — Semantic Embedding Check
  ─────────────────────────────────────────────────────
  get_embedding(comment_text)
  → compare cosine_similarity against all previously-kept embeddings
  → if any similarity > dedup_threshold (default 0.80) → SKIP

  Otherwise → KEEP
  Store embedding + keywords for future comparisons
```

The keyword check acts as a cheap pre-filter. The embedding check catches semantically similar comments that use different wording (e.g., "avoid print statements" vs. "replace print with logger").

---

## MatchingAgent

**File:** `agents/matching_agent.py`

### Responsibility

Maps each AI-generated review comment to a specific line in the actual diff. This is required because the LLM output contains `line_content` as plain text — it does not know the exact line number. The agent finds the best-matching diff line using semantic embeddings.

### Reads from context

| Field | Type |
|---|---|
| `parsed_files` | Dict[str, Any] |
| `deduped_reviews` | Dict[str, List[Dict]] |

### Writes to context

| Field | Type | Shape |
|---|---|---|
| `mapped_comments` | List[Dict] | `[{path, line, body}]` |

### How it works

```
MatchingAgent._run(context)
        │
        └── for each file in parsed_files:
              │
              ├── Pre-compute diff embeddings (once per diff line)
              │     for each line in diff_data:
              │       get_embedding(line_content) → cache
              │
              └── for each review comment in deduped_reviews[file]:
                    │
                    ├── get_embedding(review.line_content)
                    │
                    ├── cosine_similarity(review_emb, diff_emb)
                    │   for every diff line → find best_match, best_score
                    │
                    ├── best_score < match_threshold (0.75)?
                    │     → log "low-confidence match" → SKIP
                    │
                    ├── best_match has no line_number?
                    │     → SKIP
                    │
                    ├── format_severity(comment, severity)
                    │     → "🔴 **HIGH**: ..." | "🟡 **MEDIUM**: ..." | "🟢 **LOW**: ..."
                    │
                    ├── if suggestion exists:
                    │     append "\n\n```suggestion\n{suggestion}\n```"
                    │     (GitHub renders this as an inline suggestion button)
                    │
                    └── append to mapped_comments:
                          {
                            "path": best_match["file"],
                            "line": best_match["line_number"],
                            "body": formatted_comment_text
                          }
```

Diff embeddings are pre-computed **once** before the review loop. This avoids re-embedding the same diff lines for every review comment — otherwise cost would be O(reviews × diff_lines). With pre-computation, cost is O(diff_lines + reviews).

---

## CommentingAgent

**File:** `agents/commenting_agent.py`

### Responsibility

The final stage. Posts every mapped comment as an inline review comment on the GitHub PR using the GitHub REST API.

### Reads from context

| Field | Type |
|---|---|
| `owner` | str |
| `repo` | str |
| `pr_number` | str |
| `mapped_comments` | List[Dict] |
| `commit_id` | str |

### Writes to context

Nothing — this is a terminal agent. It only produces side effects (GitHub API calls).

### How it works

```
CommentingAgent._run(context)
        │
        ├── mapped_comments empty? → log "No comments to post" → return
        │
        └── post_inline_comments(owner, repo, pr_number, comments, commit_id)
              │
              └── for each comment in mapped_comments:
                    POST https://api.github.com/repos/{owner}/{repo}/pulls/{number}/comments
                    body: {
                      "path":      comment["path"],
                      "line":      comment["line"],
                      "side":      "RIGHT",
                      "body":      comment["body"],
                      "commit_id": commit_id      ← required by GitHub API
                    }
                    │
                    ├── success → log "Comment posted on line {N}"
                    └── failure → log error, continue (don't fail the whole batch)
```

`commit_id` is critical. GitHub's inline comment API requires the comment to be anchored to a specific commit SHA, not just the PR number. Without it, the API returns a 422 error.

Failures on individual comments are caught and logged but do not abort the batch — a single malformed comment should not prevent all other valid comments from being posted.

---

## Adding a New Agent

To add a new pipeline stage:

**1. Create the agent file**

```python
# agents/my_new_agent.py
from agents.base_agent import BaseAgent
from core.pr_context import PRContext


class MyNewAgent(BaseAgent):

    def __init__(self):
        super().__init__("MyNewAgent")

    def _run(self, context: PRContext) -> PRContext:
        # Read from context
        data = context.some_existing_field

        # Do work
        result = do_something(data)

        # Write to context
        context.my_new_field = result

        self.logger.debug("MyNewAgent produced %d items", len(result))
        return context
```

**2. Add the new field to PRContext**

```python
# core/pr_context.py
@dataclass
class PRContext:
    ...
    my_new_field: List[str] = field(default_factory=list)
```

**3. Insert the agent into the pipeline**

```python
# orchestrator/orchestrator.py
from agents.my_new_agent import MyNewAgent

self.pipeline = [
    FetchAgent(),
    DiffParserAgent(),
    ReviewAgent(),
    MyNewAgent(),          # ← insert at the right stage
    DeduplicationAgent(),
    MatchingAgent(),
    CommentingAgent(),
]
```

Timing, logging, and error recording are handled automatically by `BaseAgent.run()`.
