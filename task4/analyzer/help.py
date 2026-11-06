"""User guide shown by `python analyze.py help` (rich only, no network calls)."""

from __future__ import annotations

import os

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

HELP_WORDS = {"help", "guide", "usage", "/?", "-?"}


def _table(*columns: str) -> Table:
    t = Table(show_header=True, header_style="bold cyan", box=None, padding=(0, 2))
    for c in columns:
        t.add_column(c)
    return t


def show_help(console: Console, env_file_exists: bool) -> None:
    console.print(Panel.fit(
        "[bold]GitHub Repository Analyzer[/bold]  (RC3 Task 4, Track B)\n"
        "Prints a 5-section report for any public GitHub repo:\n"
        "tech stack, file structure, complexity score, dependency health, activity chart.\n"
        "Libraries: requests + rich (+ Python standard library).",
        title="analyze.py help", border_style="cyan"))

    usage = _table("Command", "What it does")
    usage.add_row("python analyze.py <repo-url>", "Analyze a repo and print the report")
    usage.add_row("python analyze.py <repo-url> --save demo\\name.txt", "Also save the report as a text file")
    usage.add_row("python analyze.py help", "Show this guide")
    usage.add_row("python analyze.py -h", "Short argparse usage")
    console.print(Panel(usage, title="Usage", border_style="green"))

    ex = _table("Example", "")
    ex.add_row("python analyze.py https://github.com/expressjs/express", "full report (npm deps)")
    ex.add_row("python analyze.py github.com/psf/requests", "scheme optional")
    ex.add_row("python analyze.py https://github.com/octocat/Hello-World.git", ".git / trailing / OK")
    ex.add_row("python analyze.py https://github.com/x/doesnotexist", "-> Repository not found (exit 3)")
    ex.add_row("python analyze.py not-a-url", "-> Invalid URL (exit 2)")
    console.print(Panel(ex, title="Examples", border_style="green"))

    # Token status: presence only, never the value.
    token_set = bool(os.environ.get("GITHUB_TOKEN"))
    status = ("[green]detected[/green] (5,000 requests/hour)" if token_set
              else "[yellow]not set[/yellow] (60 requests/hour, about 8 runs)")
    tok = _table("Option", "How")
    tok.add_row("1. .env file (recommended)",
                "Copy-Item .env.example .env   then put  GITHUB_TOKEN=<your token>  in .env and save")
    tok.add_row("2. This terminal only", '$env:GITHUB_TOKEN = "<your token>"')
    tok.add_row("3. Permanent", 'setx GITHUB_TOKEN "<your token>"   (open a new terminal after)')
    tok.add_row("Remove for this terminal", "Remove-Item Env:GITHUB_TOKEN")
    tok.add_row("Create a token", "github.com/settings/tokens (public read-only is enough)")
    console.print(Panel(tok, title=f"GITHUB_TOKEN: {status}   |   .env file: "
                                   f"{'found' if env_file_exists else 'not found'}",
                        border_style="magenta"))
    console.print("  A variable set in the shell wins over .env. The token is never printed or saved.\n")

    codes = _table("Exit code", "Meaning")
    for code, meaning in [("0", "OK"), ("1", "Unexpected error"), ("2", "Invalid URL / bad arguments"),
                          ("3", "Repository not found or private"), ("4", "GitHub rate limit reached"),
                          ("5", "Bad or expired token (401)"), ("6", "Network error"),
                          ("130", "Interrupted (Ctrl+C)")]:
        codes.add_row(code, meaning)
    console.print(Panel(codes, title="Exit codes  (check with: echo $LASTEXITCODE)", border_style="yellow"))

    files = _table("Path", "Purpose")
    files.add_row("analyze.py", "CLI entry point")
    files.add_row("analyzer\\github_client.py, fetch.py", "GitHub API calls and error handling")
    files.add_row("analyzer\\techstack.py ... activity.py", "one file per report section")
    files.add_row("analyzer\\report.py", "terminal rendering (rich)")
    files.add_row("README.md", "full documentation, formulas, limitations")
    files.add_row("demo\\", "saved example reports")
    console.print(Panel(files, title="Project files", border_style="blue"))
