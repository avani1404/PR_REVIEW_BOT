"""Shared data container that flows through the PR review pipeline.

Why a dataclass?
- Replaces ad-hoc tuples / loose kwargs with a typed, named container.
- Each pipeline stage reads what it needs and writes what it produces.
- Makes future additions (e.g., commit metadata, reviewer config) painless.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class PRContext:
    # ---- Identity (set by orchestrator before any agent runs) ----
    pr_url: str
    owner: str
    repo: str
    pr_number: str

    # ---- Fetched from GitHub ----
    commit_id: Optional[str] = None
    raw_diff: Optional[str] = None

    # ---- Built by agents during pipeline ----
    parsed_files: Dict[str, Any] = field(default_factory=dict)
    reviews_by_file: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    deduped_reviews: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    mapped_comments: List[Dict[str, Any]] = field(default_factory=list)

    # ---- Per-agent execution stats (filled by BaseAgent.run) ----
    # Example:
    #   {"FetchAgent": {"elapsed_ms": 142, "status": "ok"}, ...}
    stats: Dict[str, Dict[str, Any]] = field(default_factory=dict)

