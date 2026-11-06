"""Load KEY=value lines from a .env file next to this script into os.environ.

Variables already set in the environment win, so a real env var always overrides .env.
Values are never printed. Blank lines and lines starting with # are ignored.
"""
import os

_HERE = os.path.dirname(os.path.abspath(__file__))


def load_env(path=None):
    path = path or os.path.join(_HERE, ".env")
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key, val = key.strip(), val.strip().strip('"').strip("'")
            if key and val and not os.environ.get(key):
                os.environ[key] = val


load_env()
