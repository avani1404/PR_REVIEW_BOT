from core.github_api import post_inline_comments
from agents.base_agent import BaseAgent
from core.pr_context import PRContext


class CommentingAgent(BaseAgent):

    def __init__(self):
        super().__init__("CommentingAgent")

    def execute(self, owner, repo, pr_number, comments, commit_id):

        if not comments:
            self.logger.info("No comments to post")
            return

        post_inline_comments(owner, repo, pr_number, comments, commit_id)

    def _run(self, context: PRContext) -> PRContext:
        self.execute(
            context.owner,
            context.repo,
            context.pr_number,
            context.mapped_comments,
            context.commit_id,
        )
        return context
