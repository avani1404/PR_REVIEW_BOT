from core.deduplication import deduplicate_comments
from agents.base_agent import BaseAgent
from core.pr_context import PRContext


class DeduplicationAgent(BaseAgent):

    def __init__(self):
        super().__init__("DeduplicationAgent")

    def execute(self, reviews_by_file):

        deduped = {}

        for file_name, reviews in reviews_by_file.items():
            deduped[file_name] = deduplicate_comments(reviews)

        return deduped

    def _run(self, context: PRContext) -> PRContext:
        context.deduped_reviews = self.execute(context.reviews_by_file)
        self.logger.debug(
            "Deduplicated reviews for %d files", len(context.deduped_reviews)
        )
        return context
