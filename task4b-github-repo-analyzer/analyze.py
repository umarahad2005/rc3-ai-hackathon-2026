"""GitHub Repository Analyzer CLI (RC3 Task 4, Track B).

Usage (PowerShell):
    python analyze.py https://github.com/owner/repo [--save demo/report.txt]
    python analyze.py help        (full usage guide)

Exit codes: 0 ok, 1 unexpected, 2 invalid URL, 3 not found, 4 rate limit,
5 bad token (401), 6 network, 130 interrupted.
"""

from __future__ import annotations

import argparse
import importlib
import os
import sys
from pathlib import Path

from rich.console import Console
from rich.markup import escape

from analyzer.envfile import load_env_file
from analyzer.fetch import fetch_bundle
from analyzer.github_client import AnalyzerError, GitHubClient, parse_repo_url
from analyzer.help import HELP_WORDS, show_help

HERE = Path(__file__).resolve().parent

# (section key, module, function) in report order
SECTIONS = [
    ("techstack", "analyzer.techstack", "detect_stack"),
    ("structure", "analyzer.structure", "summarize_structure"),
    ("complexity", "analyzer.complexity", "score_complexity"),
    ("deps", "analyzer.deps", "analyze_deps"),
    ("activity", "analyzer.activity", "analyze_activity"),
]


def run_section(module_name: str, func_name: str, bundle: dict) -> dict:
    """Run one section; any exception becomes an 'unavailable' section instead of a crash."""
    try:
        func = getattr(importlib.import_module(module_name), func_name)
        result = func(bundle)
        if not isinstance(result, dict) or result.get("status") not in ("ok", "unavailable"):
            return {"status": "unavailable", "reason": "internal error: section returned an invalid result"}
        return result
    except Exception as e:  # noqa: BLE001 - one bug must not kill the whole report
        return {"status": "unavailable", "reason": f"internal error: {type(e).__name__}: {e}"}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="analyze.py",
        description="Analyze a public GitHub repository: tech stack, structure, complexity, "
                    "dependency health and contribution activity.",
    )
    p.add_argument("url", help="GitHub repository URL, e.g. https://github.com/psf/requests")
    p.add_argument("--save", metavar="PATH", help="also save the plain-text report to PATH")
    return p


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except (ValueError, OSError):
            pass
    # Optional .env next to analyze.py; never overrides variables already set in the shell.
    load_env_file(HERE / ".env")

    raw = sys.argv[1:] if argv is None else argv
    if not raw or (len(raw) == 1 and raw[0].lower() in HELP_WORDS):
        show_help(Console(), (HERE / ".env").exists())
        return 0 if raw else 2

    args = build_parser().parse_args(argv)
    console = Console(record=True)
    status_console = Console(stderr=True)  # spinners go to stderr so they never end up in --save output

    try:
        owner, repo = parse_repo_url(args.url)
        client = GitHubClient(os.environ.get("GITHUB_TOKEN"))
        with status_console.status(f"Fetching {owner}/{repo} from the GitHub API..."):
            bundle = fetch_bundle(client, owner, repo)

        sections: dict = {}
        with status_console.status("Analyzing (dependency lookups may take a few seconds)..."):
            for key, module_name, func_name in SECTIONS:
                sections[key] = run_section(module_name, func_name, bundle)

        # Honesty guard: if a root manifest exists but could not be read (rate limit, >1 MB,
        # API error) and deps found nothing, say why instead of "no manifest found".
        files_errors = bundle.get("files_errors") or {}
        if files_errors and not bundle.get("files") and sections["deps"].get("status") == "unavailable":
            sections["deps"] = {"status": "unavailable", "reason": "; ".join(files_errors.values())}

        report = importlib.import_module("analyzer.report")
        report.render(console, bundle["repo"], sections, client.token_used,
                      rate=client.rate, api_calls=client.calls)

        if args.save:
            out = Path(args.save)
            try:
                if out.parent and not out.parent.exists():
                    out.parent.mkdir(parents=True, exist_ok=True)
                console.save_text(str(out))
            except OSError as e:
                console.print(f"[bold red]Error:[/bold red] could not save report to "
                              f"{escape(str(out))} ({escape(type(e).__name__)})")
                return 1
            print(f"Report saved to {out}")
        return 0

    except AnalyzerError as e:
        prefix = "Invalid URL: " if e.exit_code == 2 else ""
        console.print(f"[bold red]Error:[/bold red] [red]{escape(prefix + str(e))}[/red]")
        return e.exit_code
    except KeyboardInterrupt:
        console.print("[red]Interrupted.[/red]")
        return 130
    except Exception as e:  # noqa: BLE001
        console.print(f"[bold red]Unexpected error:[/bold red] {escape(type(e).__name__)}: {escape(str(e))}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
