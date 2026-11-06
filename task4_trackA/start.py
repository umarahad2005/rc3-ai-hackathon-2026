"""One command to start the AI PR reviewer.

    python start.py                         # watch the demo repo, act for real
    python start.py --repo owner/name       # watch another repo
    python start.py --dry-run               # decide only, change nothing on GitHub

It does every setup step, then runs the reviewer until Ctrl+C:
  1. GITHUB_TOKEN: taken from the environment / .env, or from `gh auth token`
  2. checks GEMINI_API_KEY is set (never printed)
  3. imports every ticket in tickets/inbox -> tickets/jira
  4. watch mode: every push to a branch with a ticket key -> PR opened -> reviewed -> MERGE or BLOCK
No public URL or ngrok is needed: watch polls GitHub every few seconds.
"""
import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
sys.path.insert(0, HERE)

import config  # noqa: E402  loads .env

DEFAULT_REPO = "umarahad2005/rc3-pr-reviewer-demo"


def step(n, msg):
    print(f"[start {n}/4] {msg}", flush=True)


def _can_see(repo, tok):
    import requests
    try:
        r = requests.get(f"https://api.github.com/repos/{repo}", timeout=20,
                         headers={"Authorization": f"Bearer {tok}",
                                  "Accept": "application/vnd.github+json"})
        return r.status_code == 200
    except requests.RequestException:
        return False


def ensure_github_token(repo):
    tok = config.get("GITHUB_TOKEN")
    if tok and _can_see(repo, tok):
        return "environment/.env"
    if tok:
        print(f"   GITHUB_TOKEN from .env cannot access {repo}; trying `gh auth token`")
    try:
        env = {k: v for k, v in os.environ.items() if k not in ("GITHUB_TOKEN", "GH_TOKEN")}
        tok = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True,
                             timeout=20, env=env).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        tok = ""
    if not tok or not _can_see(repo, tok):
        sys.exit(f"No GitHub token can access {repo}. Log in once with:  gh auth login")
    os.environ["GITHUB_TOKEN"] = tok
    return "gh auth token"


def main(argv=None):
    p = argparse.ArgumentParser(description="Start the AI PR reviewer (setup + watch)")
    p.add_argument("--repo", default=config.get("WATCH_REPO", DEFAULT_REPO))
    p.add_argument("--interval", type=int, default=10, help="seconds between checks")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--once", action="store_true", help="one check, then exit (for testing)")
    p.add_argument("--all", action="store_true", help="also review branches pushed before start")
    a = p.parse_args(argv)

    step(1, f"GitHub token: OK (from {ensure_github_token(a.repo)})")

    if not config.get("GEMINI_API_KEY"):
        sys.exit("No GEMINI_API_KEY. Add it to .env (free key: https://aistudio.google.com)")
    step(2, f"Gemini key: OK, model {config.get('GEMINI_MODEL', 'gemini-2.5-flash')}")

    import ticket_import
    written, problems = ticket_import.import_inbox("tickets/inbox", "tickets/jira")
    for w in problems:
        print("   WARNING", w)
    step(3, f"Tickets: {len(written)} imported from tickets/inbox -> tickets/jira")

    mode = "DRY-RUN (no changes on GitHub)" if a.dry_run else "LIVE (status, comment, merge)"
    step(4, f"Watching {a.repo} every {a.interval}s, {mode}. Push a branch with a ticket key, "
            "e.g. feature/RC3-20-..., Ctrl+C to stop.")
    import autopilot
    try:
        autopilot.watch(a.repo, a.interval, a.dry_run, a.once, skip_existing=not a.all)
    except KeyboardInterrupt:
        print("stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
