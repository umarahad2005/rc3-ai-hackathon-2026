"""Make the task1 modules importable from tests/ regardless of the working directory."""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
