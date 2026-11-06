"""CLI: review / serve / replay / watch / import-tickets."""
import argparse
import hashlib
import hmac
import json
import sys


def main(argv=None):
    p = argparse.ArgumentParser(description="AI PR reviewer")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("review", help="review one PR")
    r.add_argument("--repo", required=True)
    r.add_argument("--pr", type=int, required=True)
    r.add_argument("--dry-run", action="store_true")
    s = sub.add_parser("serve", help="run webhook server")
    s.add_argument("--port", type=int, default=8000)
    s.add_argument("--dry-run", action="store_true")
    rp = sub.add_parser("replay", help="POST a saved webhook payload")
    rp.add_argument("payload")
    rp.add_argument("--url", default="http://localhost:8000/webhook")
    rp.add_argument("--event", default="pull_request")
    w = sub.add_parser("watch", help="poll the repo; every new push is turned into a PR and reviewed")
    w.add_argument("--repo", required=True)
    w.add_argument("--interval", type=int, default=15)
    w.add_argument("--dry-run", action="store_true")
    w.add_argument("--once", action="store_true", help="one poll, then exit")
    w.add_argument("--all", action="store_true", help="also review branches that existed before watching")
    it = sub.add_parser("import-tickets", help="convert txt/md/pdf/docx/json/csv tickets to Jira JSON")
    it.add_argument("--inbox", default="tickets/inbox")
    it.add_argument("--out", default="tickets/jira")
    a = p.parse_args(argv)

    if a.cmd == "import-tickets":
        import ticket_import
        written, problems = ticket_import.import_inbox(a.inbox, a.out)
        for line in written:
            print("imported", line)
        for line in problems:
            print("WARNING", line)
        return 0 if written and not problems else 1
    if a.cmd == "watch":
        import autopilot
        try:
            autopilot.watch(a.repo, a.interval, a.dry_run, a.once, skip_existing=not a.all)
        except KeyboardInterrupt:
            print("stopped")
        return 0

    if a.cmd == "review":
        import pipeline
        res = pipeline.review_pr(a.repo, a.pr, dry_run=a.dry_run)
        print(json.dumps(res, indent=2, default=str))
        return 0 if res["decision"] == "MERGE" else 1
    if a.cmd == "serve":
        import server
        server.serve(a.port, a.dry_run)
        return 0
    if a.cmd == "replay":
        import requests
        import config
        with open(a.payload, "rb") as f:
            body = f.read()
        headers = {"Content-Type": "application/json", "X-GitHub-Event": a.event}
        secret = config.get("WEBHOOK_SECRET")
        if secret:
            headers["X-Hub-Signature-256"] = "sha256=" + hmac.new(
                secret.encode(), body, hashlib.sha256).hexdigest()
        resp = requests.post(a.url, data=body, headers=headers, timeout=300)
        print(resp.status_code)
        print(resp.text)
        return 0 if resp.ok else 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
