"""Allows `python analyzer <url>` and `python -m analyzer <url>` as aliases of `python analyze.py <url>`."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from analyze import main  # noqa: E402

sys.exit(main())
