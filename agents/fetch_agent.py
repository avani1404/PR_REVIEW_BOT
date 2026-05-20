"""FetchAgent — first stage of the pipeline.

Responsibility:
    Talk to GitHub and populate the PRContext with:
        - commit_id  (HEAD commit SHA of the PR)
        - raw_diff   (unified diff text)

Why a dedicated agent?
    - Keeps the orchestrator free of any HTTP / GitHub details.
    - Makes the fetch step independently testable, retryable, and replaceable
      (e.g., swap REST for GraphQL, or mock in tests).
"""

from agents.base_agent import BaseAgent
from core.github_api import get_pr_head_commit, get_pr_diff
from core.pr_context import PRContext


class FetchAgent(BaseAgent):

    def __init__(self):
        super().__init__("FetchAgent")

    def _run(self, context: PRContext) -> PRContext:
        context.commit_id = get_pr_head_commit(
            context.owner, context.repo, context.pr_number
        )
        context.raw_diff = get_pr_diff(
            context.owner, context.repo, context.pr_number
        )
        self.logger.debug(
            "Fetched commit_id=%s, diff_size=%d chars",
            context.commit_id,
            len(context.raw_diff or ""),
        )

        return context

