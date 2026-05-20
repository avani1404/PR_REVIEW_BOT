from core.matching import map_comments_to_positions
from agents.base_agent import BaseAgent
from core.pr_context import PRContext


class MatchingAgent(BaseAgent):

    def __init__(self):
        super().__init__("MatchingAgent")

    def execute(self, parsed_files, deduped_reviews):

        all_comments = []

        for file_name in parsed_files:
            diff_data = parsed_files[file_name]["diff_data"]
            reviews = deduped_reviews.get(file_name, [])

            mapped = map_comments_to_positions(reviews, diff_data)

            all_comments.extend(mapped)

        return all_comments

    def _run(self, context: PRContext) -> PRContext:
        context.mapped_comments = self.execute(
            context.parsed_files, context.deduped_reviews
        )
        self.logger.debug(
            "Mapped %d inline comments", len(context.mapped_comments)
        )
        return context
