# Core Modules

The `core/` package contains all the business logic that agents delegate to. Agents are thin wrappers — the real work happens here.

---

## Table of Contents

- [pr\_context.py — Shared Pipeline Container](#pr_contextpy--shared-pipeline-container)
- [github\_api.py — GitHub REST Client](#github_apipy--github-rest-client)
- [github\_auth.py — Authentication](#github_authpy--authentication)
- [diff\_parser.py — Diff Parsing](#diff_parserpy--diff-parsing)
- [llm\_reviewer.py — LLM Prompt and Call](#llm_reviewerpy--llm-prompt-and-call)
- [json\_utils.py — Robust JSON Extractor](#json_utilspy--robust-json-extractor)
- [embedding\_utils.py — Embeddings and Similarity](#embedding_utilspy--embeddings-and-similarity)
- [deduplication.py — Comment Deduplication](#deduplicationpy--comment-deduplication)
- [matching.py — Comment-to-Line Matching](#matchingpy--comment-to-line-matching)
- [formatting.py — Severity Formatting](#formattingpy--severity-formatting)
- [security.py — Webhook Signature Verification](#securitypy--webhook-signature-verification)
- [utils.py — PR URL Parser and Fuzzy Matching](#utilspy--pr-url-parser-and-fuzzy-matching)

---

## pr\_context.py — Shared Pipeline Container

The `PRContext` dataclass is the contract between all pipeline stages. See [architecture.md](architecture.md) for the full field reference and why this pattern was chosen.

**Key design decisions:**

- `frozen=False` — agents must be able to write fields. The orchestrator owns the single instance.
- `stats` uses a plain `dict` rather than a typed nested dataclass to keep it flexible as new agents are added.
- All collection fields default to empty containers (`field(default_factory=...)`) so agents never have to guard against `None` for pipeline-internal fields. Only `commit_id` and `raw_diff` can be `None` because they come from external I/O.

---

## github\_api.py — GitHub REST Client

**File:** `core/github_api.py`

Provides three public functions used by the pipeline. All three share the same retry, auth, and error-handling infrastructure via `_request_with_retry()`.

### Public functions

```
get_pr_head_commit(owner, repo, pr_number) → str
    GET /repos/{owner}/{repo}/pulls/{number}
    Accept: application/vnd.github.v3+json
    Returns: response["head"]["sha"]

get_pr_diff(owner, repo, pr_number) → str
    GET /repos/{owner}/{repo}/pulls/{number}
    Accept: application/vnd.github.v3.diff
    Returns: raw unified diff text

post_inline_comments(owner, repo, pr_number, comments, commit_id)
    POST /repos/{owner}/{repo}/pulls/{number}/comments
    For each comment dict in the list.
    Individual failures are caught and logged — does not raise.
```

### Retry logic

```
_request_with_retry(method, url, *, headers, json_body=None)
        │
        │  tenacity decorator:
        │    stop:   after settings.github_max_retries attempts (default 5)
        │    wait:   exponential backoff
        │              min = settings.github_retry_min_wait (default 1.0s)
        │              max = settings.github_retry_max_wait (default 10.0s)
        │    retry:  on TransientGitHubError
        │                requests.exceptions.ConnectionError
        │                requests.exceptions.Timeout
        │
        ├── response.status_code in {429, 500, 502, 503, 504}?
        │     → raise TransientGitHubError  ← tenacity retries this
        │
        ├── response not ok (other 4xx)?
        │     → raise GitHubAPIError        ← tenacity does NOT retry this
        │
        └── return response
```

The separation between `TransientGitHubError` and `GitHubAPIError` is intentional. A 404 (wrong repo, wrong PR number) or 422 (malformed comment body) will never succeed on retry — raising immediately gives faster feedback.

### Auth header injection

```
_build_headers(owner, repo, accept)
    → get_token_for_repo(owner, repo)   (from github_auth.py)
    → returns {"Authorization": "{scheme} {token}", "Accept": accept}
```

The `github_api.py` module has no knowledge of JWT, App IDs, or PATs — that is entirely `github_auth.py`'s concern.

---

## github\_auth.py — Authentication

**File:** `core/github_auth.py`

Supports two auth modes. The public entry point `get_token_for_repo()` selects the best available option automatically.

### GitHub App flow

```
generate_app_jwt()
    Private key (from file or inline env var)
    RS256 JWT payload:
      iat = now - 60    (tolerate clock skew)
      exp = now + 540   (9 minutes; GitHub max is 10)
      iss = app_id

get_installation_token(installation_id)
    Check _token_cache[installation_id]:
      expires_at - now > 60s  →  return cached token
      otherwise               →  mint fresh token

    _mint_installation_token(installation_id)
      POST /app/installations/{id}/access_tokens
      Authorization: Bearer {app_jwt}
      Returns: {token, expires_at}
      Cache result.
```

### Token cache

```
_token_cache: dict[int, {"token": str, "expires_at": int}]
```

Access is protected by `threading.Lock()`. The cache is process-wide (module-level). This is appropriate because the webhook server runs multiple threads (one per incoming request), and installation tokens are safe to share — they are not user-specific.

### Installation ID discovery

If `GITHUB_APP_INSTALLATION_ID` is not set, the App queries GitHub to find which installation covers the target repo:

```
GET /repos/{owner}/{repo}/installation
Authorization: Bearer {app_jwt}
→ response["id"]  (installation ID)
```

This call is made once per repo per process lifetime (the result is passed to `get_installation_token()` which caches it).

---

## diff\_parser.py — Diff Parsing

**File:** `core/diff_parser.py`

Three functions used by `DiffParserAgent`.

### split\_diff\_by\_file(diff\_text)

Scans the raw diff for `diff --git` header lines and splits the monolithic diff into one chunk per file.

```
Input:
  "diff --git a/core/utils.py b/core/utils.py\n..."
  "diff --git a/agents/base_agent.py b/agents/base_agent.py\n..."

Output:
  {
    "core/utils.py":      "...(diff content for utils.py)...",
    "agents/base_agent.py": "...(diff content for base_agent.py)..."
  }
```

The file path is extracted from the third token of the `diff --git` header (`a/core/utils.py` → strip the `a/` prefix → `core/utils.py`).

### clean\_diff(diff\_text)

Removes lines that cause `unidiff.PatchSet` to raise a parse error:

- `new file mode ...`
- `deleted file mode ...`
- `index abc1234..def5678 ...`

These are valid git diff metadata lines but `unidiff` does not expect them when parsing a single-file diff chunk (i.e., a chunk that has already been separated from the full diff by `split_diff_by_file`).

### extract\_diff\_with\_positions(diff\_text)

The core parsing function. Uses `unidiff.PatchSet` to walk the diff structure and extract every added line with its exact line number and diff position.

```
for file in PatchSet(cleaned_diff):
  for hunk in file:
    position = 0
    for line in hunk:
      position += 1           ← increments for ALL lines (added, removed, context)
      if line.is_added:
        if line.target_line_no is None: continue
        normalize whitespace on line.value
        append {file, line_content, line_number, position}
```

**Why position increments for every line, not just added lines:**
GitHub's inline comment API uses `position` to place comments within the diff view. Position 1 is the first line of the first hunk. It counts every visible line — context lines, removed lines, and added lines all count. Using only added-line positions would produce off-by-N placement errors.

---

## llm\_reviewer.py — LLM Prompt and Call

**File:** `core/llm_reviewer.py`

### review\_file(file\_name, diff) → str

Builds a detailed prompt and calls the local Ollama LLM. Returns the raw string response (not yet parsed).

### Prompt structure

The prompt uses aggressive, explicit instructions because LLMs tend to be lenient code reviewers by default. Key sections:

```
You are a STRICT and HIGHLY CRITICAL senior backend code reviewer.

CRITICAL OUTPUT RULES:
  1. Output must be a strict JSON array only
  2. No markdown fences (no ```json)
  3. No comments (no // or #)
  4. No trailing commas
  5. No explanation outside JSON

LINE MATCHING RULE:
  "line_content" must match the EXACT added line from the diff.
  ❌ WRONG:  "line_content": "check user null"
  ✅ CORRECT: "line_content": "if user == None:"

REVIEW GUIDELINES: code quality, security, performance, style,
  edge cases, error handling, naming, duplicate logic, etc.

SEVERITY RULES:
  high   → security issues, crashes, incorrect logic
  medium → bad practices, maintainability
  low    → readability, style
```

The strictness about `line_content` format is critical: the matching step uses this string to find the corresponding diff line via semantic similarity. If the LLM rephrases or summarizes the line, the match score drops and the comment gets discarded.

### LLM call

```python
ollama.chat(
    model=settings.llm_model,      # default: "llama3"
    messages=[
        {"role": "system", "content": "You are an expert backend code reviewer."},
        {"role": "user",   "content": prompt}
    ]
)
```

The response is `response['message']['content']` — a raw string that may or may not be valid JSON. `json_utils.py` handles the cleanup.

---

## json\_utils.py — Robust JSON Extractor

**File:** `core/json_utils.py`

### extract\_json\_from\_text(text) → list

LLM outputs are not always valid JSON. This function implements a multi-stage extraction strategy to recover as much structured data as possible.

```
Stage 1 — Strip inline comments
  re.sub(r'//.*', '', text)    remove // comments
  re.sub(r'#.*',  '', text)    remove # comments

Stage 2 — Fix print() quotes
  print("...") inside a JSON string breaks the parser because of the
  unescaped inner quotes. Regex replaces them with escaped versions.

Stage 3 — Find JSON array boundaries
  text.find("[")   → start
  text.rfind("]")  → end
  If either is -1 → return []

Stage 4 — Standard json.loads()
  Try to parse the extracted slice as-is.
  Success → return parsed list.
  Failure → fall through to Stage 5.

Stage 5 — Object-by-object fallback
  re.findall(r'\{[^\}]*\}', json_str)
  Parse each object individually.
  Fix trailing commas:  re.sub(r',\s*}', '}', obj)
  Fix quote escaping:   obj.replace('("', '(\\"')
  Collect successfully-parsed objects.
  Return list (may be partial — some objects may fail individually).
```

Stage 5 is the safety net. If the LLM produces an almost-valid JSON array where one object is malformed, Stage 5 recovers the valid objects and discards only the broken one. This is better than losing the entire review result.

---

## embedding\_utils.py — Embeddings and Similarity

**File:** `core/embedding_utils.py`

### get\_embedding(text) → list[float]

```
normalize: " ".join(text.split())
empty?    → return []
otherwise → _get_embedding_cached(normalized_text)
              → ollama.embeddings(model=embedding_model, prompt=text)
              → response["embedding"]
```

The LRU cache is applied at module import time using `lru_cache(maxsize=settings.embedding_cache_size)`. Cache size defaults to 2048 entries. Identical lines (e.g., `pass`, `return None`) are embedded only once per process lifetime regardless of how many files contain them.

### cosine\_similarity(vec1, vec2) → float

```
dot  = Σ(a * b)  for a, b in zip(vec1, vec2)
norm1 = √Σ(a²)
norm2 = √Σ(b²)

if norm1 == 0 or norm2 == 0: return 0
return dot / (norm1 * norm2)
```

Returns a value in `[-1.0, 1.0]`. In practice, text embeddings from `nomic-embed-text` produce values in `[0.0, 1.0]`. A score of 1.0 means identical. A score near 0 means unrelated.

The zero-vector guard prevents division-by-zero when `get_embedding()` returns `[]` for an empty string that somehow passes the normalization check.

---

## deduplication.py — Comment Deduplication

**File:** `core/deduplication.py`

### deduplicate\_comments(ai\_reviews, threshold=None) → list

Runs two-stage deduplication on a list of review dicts for a single file. See [agents.md — DeduplicationAgent](agents.md#deduplicationagent) for the full algorithm diagram.

The `threshold` parameter defaults to `settings.dedup_threshold` (0.80) but can be overridden per-call for testing.

**Keyword extraction logic:**

```
"print" | "logging" | "logger"  →  "logging"
"variable" | "name"             →  "naming"
"none"                          →  "none_check"
"performance" | "optimize"      →  "performance"
```

These keywords are deliberately coarse. The goal is to prevent obvious category-level duplicates (three different "use logging instead of print" comments) cheaply, before paying the cost of an embedding call.

**Known limitation:** The keyword set is hardcoded and small. It does not cover all possible duplicate patterns (e.g., multiple comments about missing type hints). The embedding similarity check is the real deduplication workhorse — keywords are just the fast pre-filter.

---

## matching.py — Comment-to-Line Matching

**File:** `core/matching.py`

### map\_comments\_to\_positions(ai\_reviews, diff\_data) → list[dict]

Maps AI review comments (which contain only plain-text line content) to exact diff line numbers by semantic similarity.

See [agents.md — MatchingAgent](agents.md#matchingagent) for the full algorithm. Key efficiency note: diff embeddings are pre-computed once before the review loop, reducing embedding calls from O(reviews × diff\_lines) to O(diff\_lines + reviews).

**Output shape per comment:**

```python
{
    "path": "core/utils.py",     # file path (from best_match["file"])
    "line": 42,                  # exact line number (int)
    "body": "🟡 **MEDIUM**: ..." # formatted comment with optional suggestion block
}
```

---

## formatting.py — Severity Formatting

**File:** `core/formatting.py`

### format\_severity(comment, severity) → str

Prepends a severity badge to a comment string.

```
"high"   →  "🔴 **HIGH**: {comment}"
"medium" →  "🟡 **MEDIUM**: {comment}"
other    →  "🟢 **LOW**: {comment}"
```

The `matching.py` module also appends a GitHub suggestion block when a `suggestion` field is present:

```markdown
🟡 **MEDIUM**: Avoid using print statements in production code.

```suggestion
logger.info("Logged in")
```
```

GitHub renders the ` ```suggestion ` block as a clickable "Apply suggestion" button that directly commits the fix.

---

## security.py — Webhook Signature Verification

**File:** `core/security.py`

### verify\_github\_signature(raw\_body, signature\_header, secret) → bool

Verifies that a webhook payload was sent by GitHub and not a third party.

```
Inputs:
  raw_body:          exact request body bytes (not re-serialized)
  signature_header:  value of X-Hub-Signature-256 header
  secret:            WEBHOOK_SECRET from settings

Algorithm:
  1. secret empty?              → return False (caller handles dev mode)
  2. header missing or no "sha256=" prefix? → log warning → return False
  3. extract received_sig from header (after "sha256=")
  4. compute expected_sig:
       hmac.new(
         key=secret.encode("utf-8"),
         msg=raw_body,
         digestmod=hashlib.sha256
       ).hexdigest()
  5. hmac.compare_digest(received_sig, expected_sig)
       → constant-time comparison (prevents timing attacks)
       → return True if equal, False otherwise
```

**Why constant-time comparison matters:**
A naive `==` string comparison short-circuits on the first mismatched character. An attacker can measure response times to learn how many characters of their forged signature are correct, progressively building up the right value. `hmac.compare_digest()` always takes the same time regardless of where the strings differ.

**Why `raw_body` must be the exact bytes:**
GitHub computes the HMAC over the raw request body. If you parse the JSON and re-serialize it, field ordering or whitespace may differ, producing a different HMAC even for a legitimate payload.

---

## utils.py — PR URL Parser and Fuzzy Matching

**File:** `core/utils.py`

### parse\_pr\_url(pr\_url) → (owner, repo, pr\_number)

Splits a GitHub PR URL into its three components.

```
Input:  "https://github.com/myorg/myrepo/pull/42"
Split:  ["https:", "", "github.com", "myorg", "myrepo", "pull", "42"]
Index:   0         1   2             3        4         5       6
Output: ("myorg", "myrepo", "42")
```

This is a simple string split — it does not validate the URL format. Malformed URLs will produce incorrect indices and likely cause a downstream error.

### is\_similar(a, b, threshold=85) → bool

```
from rapidfuzz import fuzz
return fuzz.ratio(a, b) >= threshold
```

`fuzz.ratio()` returns a similarity score from 0 to 100. The default threshold of 85 means the strings must be at least 85% similar character-by-character.

This function is available for fuzzy matching of LLM output against actual code lines as a fallback, but the primary matching mechanism in `matching.py` uses semantic embeddings (cosine similarity), not fuzzy string matching.
