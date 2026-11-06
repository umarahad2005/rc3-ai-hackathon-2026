import hashlib
import hmac
import json
import threading
import urllib.error
import urllib.request

import pytest

import pipeline
import server

SECRET = "s3cret"


@pytest.fixture
def srv(monkeypatch):
    seen = []

    def fake_review(repo, number, dry_run=False, call=None):
        seen.append((repo, number, dry_run))
        return {"ticket_id": "TASK-004", "decision": "BLOCK", "reason": "test",
                "actions": [], "verdict": None}

    monkeypatch.setattr(pipeline, "review_pr", fake_review)
    monkeypatch.setenv("WEBHOOK_SECRET", SECRET)
    s = server.make_server(port=0, dry_run=True, host="127.0.0.1")
    t = threading.Thread(target=s.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{s.server_address[1]}", seen
    s.shutdown()
    s.server_close()


def payload(action="opened"):
    return {"action": action, "number": 7,
            "repository": {"full_name": "acme/shop"},
            "pull_request": {"number": 7, "title": "TASK-004 login", "head": {"ref": "feature/TASK-004"}}}


def sign(body, secret=SECRET):
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def post(base, body, event="pull_request", sig=None):
    headers = {"Content-Type": "application/json", "X-GitHub-Event": event}
    if sig:
        headers["X-Hub-Signature-256"] = sig
    req = urllib.request.Request(base + "/webhook", data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def test_valid_signature_runs_review(srv):
    base, seen = srv
    body = json.dumps(payload()).encode()
    code, data = post(base, body, sig=sign(body))
    assert code == 200 and data["decision"] == "BLOCK"
    assert seen == [("acme/shop", 7, True)]


def test_invalid_signature_401(srv):
    base, seen = srv
    body = json.dumps(payload()).encode()
    assert post(base, body, sig=sign(body, "wrong"))[0] == 401
    assert post(base, body)[0] == 401
    assert seen == []


def test_ignored_event(srv):
    base, seen = srv
    body = json.dumps({"zen": "hi"}).encode()
    code, data = post(base, body, event="ping", sig=sign(body))
    assert code == 200 and "ignored" in data
    body = json.dumps(payload("closed")).encode()
    code, data = post(base, body, sig=sign(body))
    assert code == 200 and "ignored" in data
    assert seen == []


def test_bad_json_400(srv):
    base, seen = srv
    body = b"{not json"
    assert post(base, body, sig=sign(body))[0] == 400


def test_health(srv):
    base, _ = srv
    with urllib.request.urlopen(base + "/health", timeout=10) as r:
        assert r.status == 200


def test_verify_signature_unit():
    body = b"abc"
    assert server.verify_signature(SECRET, body, sign(body))
    assert not server.verify_signature(SECRET, body, sign(body, "x"))
    assert not server.verify_signature(SECRET, body, None)
