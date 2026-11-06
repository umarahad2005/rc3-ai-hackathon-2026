"""Configuration from environment variables only. Never print secrets."""
import os

import envfile  # noqa: F401  loads .env (if present); real env vars win


def get(name, default=None):
    val = os.environ.get(name)
    if val is None or val.strip() == "":
        return default
    return val.strip()


def _int(name, default):
    try:
        return int(get(name, default))
    except (TypeError, ValueError):
        return default


MAX_DIFF_CHARS = _int("MAX_DIFF_CHARS", 60000)
STATUS_CONTEXT = "ai-pr-reviewer"
