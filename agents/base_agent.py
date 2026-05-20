import logging
import time

from core.pr_context import PRContext


class BaseAgent:
    """Base class for all pipeline agents.

    Contract
    --------
    Subclasses implement `_run(context) -> PRContext`.
    The public `run(context)` provided here is a *template method* that:
        - logs start / finish
        - measures elapsed time
        - records per-stage stats on the context
        - handles exceptions in one place

    The legacy `execute(...)` API is kept temporarily for backward
    compatibility while older code is migrated.
    """

    def __init__(self, name):
        self.name = name
        self.logger = logging.getLogger(f"agents.{name}")

    def run(self, context: PRContext) -> PRContext:
        self.logger.info("%s started", self.name)
        start = time.perf_counter()
        status = "ok"
        error = None
        try:
            context = self._run(context)
            return context
        except Exception as exc:
            status = "error"
            error = repr(exc)
            self.logger.exception("%s failed", self.name)
            raise
        finally:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            context.stats[self.name] = {
                "elapsed_ms": elapsed_ms,
                "status": status,
                "error": error,
            }
            self.logger.info(
                "%s finished in %d ms (status=%s)",
                self.name,
                elapsed_ms,
                status,
            )

    def _run(self, context: PRContext) -> PRContext:
        """Subclass hook — implement actual agent work here."""
        raise NotImplementedError(
            f"{self.name}._run(context) must be implemented by subclasses."
        )

    def execute(self, *args, **kwargs):
        """Legacy entry point kept for backward compatibility.

        Subclasses that have not yet migrated still override execute(...).
        Once everything is on PRContext, this can be removed.
        """
        raise NotImplementedError