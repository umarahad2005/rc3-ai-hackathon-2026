"""Tiny stdlib-only .env loader (no python-dotenv).

Reads KEY=VALUE lines, ignores blank lines and # comments, strips one pair of
matching surrounding quotes, accepts an optional leading "export ", and never
overrides a variable that is already set in os.environ. Values are never printed.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def load_env_file(path: str | os.PathLike) -> list[str]:
    """Load KEY=VALUE pairs from `path` into os.environ.

    Returns the list of key NAMES that were set (never the values).
    A missing or unreadable file is silently ignored (returns []).
    """
    p = Path(path)
    if not p.is_file():
        return []
    try:
        text = p.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return []

    loaded: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not _KEY_RE.match(key):
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        if key in os.environ:
            continue  # never override what the shell already set
        os.environ[key] = value
        loaded.append(key)
    return loaded
