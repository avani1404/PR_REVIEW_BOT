from agents.fetch_agent import FetchAgent
from agents.diff_parser_agent import DiffParserAgent
from agents.review_agent import ReviewAgent
from agents.dedup_agent import DeduplicationAgent
from agents.matching_agent import MatchingAgent
from agents.commenting_agent import CommentingAgent

# 🔥 Single source of truth for parse_pr_url — imported from core/utils.py
# instead of being duplicated here. This follows the DRY principle:
# fixing/improving the function in one place updates the entire system.
from core.utils import parse_pr_url
from core.pr_context import PRContext
import logging


logger = logging.getLogger(__name__)


class OrchestratorAgent:

    def __init__(self):
        # Pipeline stages run in order. Each stage reads/writes PRContext.
        self.pipeline = [
            FetchAgent(),
            DiffParserAgent(),
            ReviewAgent(),
            DeduplicationAgent(),
            MatchingAgent(),
            CommentingAgent(),
        ]

    def run(self, pr_url):

        owner, repo, pr_number = parse_pr_url(pr_url)

        context = PRContext(
            pr_url=pr_url,
            owner=owner,
            repo=repo,
            pr_number=pr_number,
        )

        logger.info(
            "Starting pipeline for %s/%s PR #%s", owner, repo, pr_number
        )

        for agent in self.pipeline:
            context = agent.run(context)

        return context
