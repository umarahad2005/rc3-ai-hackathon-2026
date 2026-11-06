import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


import pytest  # noqa: E402

_ENV_FROM_DOTENV = ("JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN", "JIRA_TICKETS_DIR", "TICKETS_CSV",
                    "WEBHOOK_SECRET", "GITHUB_TOKEN", "GEMINI_API_KEY", "GEMINI_MODEL", "MAX_DIFF_CHARS")


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """Offline tests must not see the user's real .env / environment settings."""
    for k in _ENV_FROM_DOTENV:
        monkeypatch.delenv(k, raising=False)
