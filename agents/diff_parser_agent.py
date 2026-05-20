from core.diff_parser import split_diff_by_file, extract_diff_with_positions
from agents.base_agent import BaseAgent
from core.pr_context import PRContext


class DiffParserAgent(BaseAgent):

    def __init__(self):
        super().__init__("DiffParserAgent")

    def execute(self, diff_text):

        files = split_diff_by_file(diff_text)

        parsed = {}

        for file_name, file_diff in files.items():
            parsed[file_name] = {
                "raw_diff": file_diff,
                "diff_data": extract_diff_with_positions(file_diff)
            }

        return parsed

    def _run(self, context: PRContext) -> PRContext:
        context.parsed_files = self.execute(context.raw_diff or "")
        self.logger.debug("Parsed %d files from diff", len(context.parsed_files))
        return context
