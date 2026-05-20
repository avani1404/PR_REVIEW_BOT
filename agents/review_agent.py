# 🔥 Import each function from the file where it ACTUALLY lives:
#   - review_file → llm_reviewer.py (handles LLM API calls)
#   - extract_json_from_text → json_utils.py (handles JSON cleanup)
# The previous combined import would crash with ImportError because
# extract_json_from_text was never defined in llm_reviewer.py.
from core.llm_reviewer import review_file
from core.json_utils import extract_json_from_text
from agents.base_agent import BaseAgent
from core.pr_context import PRContext


class ReviewAgent(BaseAgent):

    def __init__(self):
        super().__init__("ReviewAgent")

    def execute(self, parsed_files):

        reviews = {}

        for file_name, data in parsed_files.items():
            raw_diff = data["raw_diff"]

            response = review_file(file_name, raw_diff)

            ai_reviews = extract_json_from_text(response)

            if ai_reviews:
                reviews[file_name] = ai_reviews

        return reviews

    def _run(self, context: PRContext) -> PRContext:
        context.reviews_by_file = self.execute(context.parsed_files)
        self.logger.debug(
            "Generated reviews for %d files", len(context.reviews_by_file)
        )
        return context
