"""Push -> PR -> review -> merge/block, fully automatic.

handle_push(repo, branch, sha): called by the webhook (GitHub "push" event) and by watch mode.
  1. ignore the default branch and branches/commits without a ticket key
  2. find the open PR for the branch, or open one automatically (title = branch's ticket key + commit msg)
  3. run pipeline.review_pr -> MERGE (status success + comment + merge) or BLOCK (status failure + comment)
watch(repo, interval): polls GitHub every `interval` seconds for new pushes, so the automation
  works on a laptop with no public URL (GitHub webhooks cannot reach localhost without a tunnel).
"""
import json
import os
import time

import code_fetcher
import pipeline
import story_fetcher

AUTO_MARKER = "Opened automatically by ai-pr-reviewer"
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".watch_state.json")


def _log(msg):
    print(f"[auto] {msg}", flush=True)


def default_branch(repo):
    return code_fetcher.gh("GET", f"/repos/{repo}").json().get("default_branch", "main")


def find_or_open_pr(repo, branch, base, dry_run=False):
    owner = repo.split("/")[0]
    prs = code_fetcher.gh("GET", f"/repos/{repo}/pulls", params={"head": f"{owner}:{branch}", "state": "open"}).json()
    if prs:
        return prs[0]["number"], False
    commit = code_fetcher.gh("GET", f"/repos/{repo}/commits/{branch}").json()
    msg = ((commit.get("commit") or {}).get("message") or branch).splitlines()[0]
    key = story_fetcher.extract_ticket_id(branch, msg)
    title = msg if key and key in msg else f"{key} {msg}"
    if dry_run:
        _log(f"[DRY-RUN] would open PR '{title}' {branch} -> {base}")
        return None, True
    pr = code_fetcher.gh("POST", f"/repos/{repo}/pulls", json={
        "title": title, "head": branch, "base": base,
        "body": f"{AUTO_MARKER} for ticket {key} after a push to `{branch}`."}).json()
    _log(f"opened PR #{pr['number']} '{title}'")
    return pr["number"], True


def open_pr_number(repo, branch):
    owner = repo.split("/")[0]
    prs = code_fetcher.gh("GET", f"/repos/{repo}/pulls", params={"head": f"{owner}:{branch}", "state": "open"}).json()
    return prs[0]["number"] if prs else None


def handle_push(repo, branch, sha=None, dry_run=False, base=None, skip_if_pr_exists=False):
    """skip_if_pr_exists=True is used by the webhook: when the branch already has an open PR,
    GitHub also sends pull_request/synchronize for this push, and that event does the review."""
    base = base or default_branch(repo)
    if branch == base:
        _log(f"push to {base} - nothing to review")
        return {"ignored": f"push to default branch {base}"}
    if skip_if_pr_exists:
        existing = open_pr_number(repo, branch)
        if existing:
            _log(f"push to {branch}: PR #{existing} already open - its pull_request event reviews it")
            return {"ignored": f"PR #{existing} already open; reviewed via pull_request event"}
    key = story_fetcher.extract_ticket_id(branch, "")
    _log(f"push {repo}@{branch} {str(sha or '')[:7]} ticket={key}")
    number, _ = find_or_open_pr(repo, branch, base, dry_run)
    if number is None:
        return {"ignored": "dry-run: PR not opened"}
    return pipeline.review_pr(repo, number, dry_run=dry_run)


def _load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=1)


def poll_once(repo, state, dry_run=False, base=None):
    """Review every non-default branch whose head SHA has not been reviewed yet."""
    base = base or default_branch(repo)
    results = []
    for b in code_fetcher.gh("GET", f"/repos/{repo}/branches", params={"per_page": 100}).json():
        name, sha = b["name"], b["commit"]["sha"]
        if name == base or state.get(f"{repo}:{name}") == sha:
            continue
        state[f"{repo}:{name}"] = sha  # mark first, so a crash never loops on the same push
        _save_state(state)
        try:
            results.append(handle_push(repo, name, sha, dry_run, base))
        except Exception as e:  # report and keep watching
            _log(f"ERROR on {name}: {type(e).__name__}: {e}")
    return results


def watch(repo, interval=15, dry_run=False, once=False, skip_existing=True):
    state = _load_state()
    base = default_branch(repo)
    if skip_existing and not any(k.startswith(repo + ":") for k in state):
        for b in code_fetcher.gh("GET", f"/repos/{repo}/branches", params={"per_page": 100}).json():
            state[f"{repo}:{b['name']}"] = b["commit"]["sha"]
        _save_state(state)
        _log(f"baseline taken: existing branches are not re-reviewed; only NEW pushes are")
    _log(f"watching {repo} (default branch {base}) every {interval}s - push a branch like feature/RC3-5-x")
    while True:
        poll_once(repo, state, dry_run, base)
        if once:
            return
        time.sleep(interval)
