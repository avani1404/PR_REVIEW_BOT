import logging

from config.settings import get_settings


_CONFIGURED = False


def configure_logging(level=None):
    """Configure app-wide logging once, with env-overridable defaults."""
    global _CONFIGURED

    if _CONFIGURED:
        return

    settings = get_settings()

    resolved_level = level or settings.log_level

    if isinstance(resolved_level, str):
        resolved_level = resolved_level.upper()

    log_format = settings.log_format

    logging.basicConfig(level=resolved_level, format=log_format)
    _CONFIGURED = True

