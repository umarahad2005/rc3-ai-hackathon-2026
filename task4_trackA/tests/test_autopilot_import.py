import json

import autopilot
import ticket_import as ti


def test_txt_ticket_parsed(tmp_path):
    t = ti.parse_ticket_text("Key: RC3-7\nSummary: Cancel\n\nAcceptance Criteria:\n- A one\n- B two\n\nNotes:\nx")
    assert t["key"] == "RC3-7" and t["summary"] == "Cancel" and t["acceptance_criteria"] == ["A one", "B two"]


def test_no_ac_means_none_and_no_key_skipped(tmp_path):
    inbox, out = tmp_path / "in", tmp_path / "out"
    inbox.mkdir()
    (inbox / "a.txt").write_text("RC3-1 Title\nno criteria here")
    (inbox / "b.txt").write_text("nothing")
    written, problems = ti.import_inbox(str(inbox), str(out))
    import story_fetcher
    d = json.loads((out / "RC3-1.json").read_text())
    assert story_fetcher.parse_ac(d["fields"]["description"]) == []  # reviewer will block
    assert any("no ticket key" in p for p in problems)


def test_push_to_default_branch_ignored(monkeypatch):
    called = []
    monkeypatch.setattr(autopilot.pipeline, "review_pr", lambda *a, **k: called.append(a))
    assert "ignored" in autopilot.handle_push("o/r", "main", "abc", base="main")
    assert not called


def test_push_reuses_open_pr_then_reviews(monkeypatch):
    class R:
        def __init__(self, d): self.d = d
        def json(self): return self.d
    monkeypatch.setattr(autopilot.code_fetcher, "gh", lambda m, p, **k: R([{"number": 5}]))
    monkeypatch.setattr(autopilot.pipeline, "review_pr", lambda repo, n, dry_run=False: {"decision": "BLOCK", "pr": n})
    assert autopilot.handle_push("o/r", "feature/RC3-7-x", "abc", base="main")["pr"] == 5


def test_webhook_push_skips_when_pr_already_open(monkeypatch):
    class R:
        def json(self): return [{"number": 9}]
    monkeypatch.setattr(autopilot.code_fetcher, "gh", lambda m, p, **k: R())
    monkeypatch.setattr(autopilot.pipeline, "review_pr", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no review")))
    res = autopilot.handle_push("o/r", "feature/RC3-7-x", "abc", base="main", skip_if_pr_exists=True)
    assert "already open" in res["ignored"]


def test_server_ignores_pr_opened_by_tool():
    import json as _j
    import threading
    import requests
    import server
    srv = server.make_server(0, dry_run=True, host="127.0.0.1")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        body = _j.dumps({"action": "opened", "number": 3, "repository": {"full_name": "o/r"},
                         "pull_request": {"number": 3, "body": autopilot.AUTO_MARKER + " for ticket RC3-1"}})
        r = requests.post(f"http://127.0.0.1:{srv.server_address[1]}/webhook", data=body,
                          headers={"X-GitHub-Event": "pull_request", "Content-Type": "application/json"}, timeout=10)
        assert r.status_code == 200 and "push handler" in r.json()["ignored"]
    finally:
        srv.shutdown()
