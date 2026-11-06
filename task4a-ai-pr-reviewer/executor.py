"""Act on a review verdict: set commit status, comment, and merge (only on a real pass)."""
import code_fetcher
import config

FAIL_HEADER = "## AI review: FAILED - merge blocked"
PASS_HEADER = "## AI review: PASSED"


def _context():
    return getattr(config, "STATUS_CONTEXT", "ai-pr-reviewer")


def _short(text, limit=140):
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def is_pass(verdict):
    return isinstance(verdict, dict) and verdict.get("fulfilled") is True and not verdict.get("error")


def act(repo, pr, verdict, dry_run=False):
    """Apply the verdict to the PR. Returns a human-readable list of actions."""
    number = pr["number"]
    sha = pr.get("head_sha")
    feedback = verdict.get("feedback") or ""
    reason = verdict.get("reason") or verdict.get("error") or "Acceptance criteria not fulfilled"
    prefix = "[DRY-RUN] " if dry_run else ""
    log = []

    if is_pass(verdict):
        steps = [
            ("POST", f"/repos/{repo}/statuses/{sha}",
             {"state": "success", "context": _context(),
              "description": "AI review passed: acceptance criteria fulfilled"},
             f"status success on {str(sha)[:7]}"),
            ("POST", f"/repos/{repo}/issues/{number}/comments",
             {"body": f"{PASS_HEADER}\n\n{feedback}".strip()},
             f"comment PASSED on PR #{number}"),
            ("PUT", f"/repos/{repo}/pulls/{number}/merge",
             {"merge_method": "squash", "sha": sha} if sha else {"merge_method": "squash"},
             f"squash-merge PR #{number}"),
        ]
    else:
        body = f"{FAIL_HEADER}\n\n**Reason:** {reason}\n"
        if feedback:
            body += f"\n{feedback}\n"
        steps = [
            ("POST", f"/repos/{repo}/statuses/{sha}",
             {"state": "failure", "context": _context(),
              "description": _short(f"AI review blocked: {reason}")},
             f"status failure on {str(sha)[:7]}"),
            ("POST", f"/repos/{repo}/issues/{number}/comments",
             {"body": body}, f"comment FAILED on PR #{number}"),
        ]

    for method, path, payload, label in steps:
        if dry_run:
            log.append(f"{prefix}{method} {path} ({label})")
            continue
        code_fetcher.gh(method, path, json=payload)
        log.append(f"{method} {path} ({label})")
    return log
