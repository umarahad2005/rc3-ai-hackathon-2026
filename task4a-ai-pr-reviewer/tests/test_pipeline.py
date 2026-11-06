import json

import pytest
import requests

import code_fetcher as cf
import executor
import pipeline
import story_fetcher as sf

REPO = "acme/shop"
PR = {"number": 7, "title": "Add login", "head_ref": "feature/TASK-004-login",
      "head_sha": "abc1234def", "base_ref": "main", "state": "open", "merged": False}
TICKET = {"id": "TASK-004", "title": "Login", "description": "x",
          "acceptance_criteria": ["User can log in", "Bad password shows error"], "source": "csv"}
DIFF = "diff --git a/app.py b/app.py\n+def login(): pass\n"


@pytest.fixture
def env(monkeypatch):
    calls = []

    def fake_gh(method, path, **kw):
        calls.append((method, path, kw.get("json")))

        class R:
            status_code = 200

            def json(self):
                return {}
        return R()

    def no_network(*a, **k):
        raise AssertionError("network access attempted")

    monkeypatch.setattr(requests, "request", no_network)
    monkeypatch.setattr(cf, "gh", fake_gh)
    monkeypatch.setattr(cf, "fetch_pr", lambda repo, n: dict(PR))
    monkeypatch.setattr(cf, "fetch_diff", lambda repo, n: DIFF)
    monkeypatch.setattr(sf, "fetch_ticket", lambda tid: dict(TICKET))
    monkeypatch.delenv("MAX_DIFF_CHARS", raising=False)
    return calls


def llm(text):
    return lambda system, user: text


PASS = llm(json.dumps({"fulfilled": True, "feedback": "All AC met."}))


def assert_blocked(res, calls):
    assert res["decision"] == "BLOCK"
    assert res["reason"]
    assert res["verdict"]["fulfilled"] is not True
    assert not any(m == "PUT" for m, _, _ in calls), "merge must not be called"
    status = [j for m, p, j in calls if "/statuses/" in p]
    assert status and status[0]["state"] == "failure"
    assert len(status[0]["description"]) <= 140
    comments = [j for m, p, j in calls if p.endswith("/comments")]
    assert comments and comments[0]["body"].startswith("## AI review: FAILED - merge blocked")


def test_merge_when_fulfilled_true(env):
    res = pipeline.review_pr(REPO, 7, call=PASS)
    assert res["decision"] == "MERGE"
    assert res["ticket_id"] == "TASK-004"
    methods = [(m, p) for m, p, _ in env]
    assert ("PUT", f"/repos/{REPO}/pulls/7/merge") in methods
    put = [j for m, p, j in env if m == "PUT"][0]
    assert put["merge_method"] == "squash"
    st = [j for m, p, j in env if "/statuses/" in p][0]
    assert st["state"] == "success" and st["context"] == "ai-pr-reviewer"
    assert methods[-1][0] == "PUT"  # merge happens last


def test_no_ticket_id(env, monkeypatch):
    monkeypatch.setattr(cf, "fetch_pr", lambda r, n: dict(PR, head_ref="feature/login", title="Add login"))
    res = pipeline.review_pr(REPO, 7, call=PASS)
    assert_blocked(res, env)
    assert "ticket" in res["reason"].lower()


def test_ticket_not_found(env, monkeypatch):
    def boom(tid):
        raise sf.TicketError("ticket TASK-004 not found")
    monkeypatch.setattr(sf, "fetch_ticket", boom)
    res = pipeline.review_pr(REPO, 7, call=PASS)
    assert_blocked(res, env)
    assert "not found" in res["reason"]


def test_empty_ac(env, monkeypatch):
    monkeypatch.setattr(sf, "fetch_ticket", lambda tid: dict(TICKET, acceptance_criteria=[]))
    res = pipeline.review_pr(REPO, 7, call=PASS)
    assert_blocked(res, env)
    assert "acceptance criteria" in res["reason"].lower()


def test_diff_github_error(env, monkeypatch):
    def boom(r, n):
        raise cf.GitHubError("GitHub GET -> 404: Not Found")
    monkeypatch.setattr(cf, "fetch_diff", boom)
    assert_blocked(pipeline.review_pr(REPO, 7, call=PASS), env)


def test_empty_diff(env, monkeypatch):
    monkeypatch.setattr(cf, "fetch_diff", lambda r, n: "   \n")
    assert_blocked(pipeline.review_pr(REPO, 7, call=PASS), env)


def test_oversized_diff(env, monkeypatch):
    monkeypatch.setenv("MAX_DIFF_CHARS", "100")
    monkeypatch.setattr(cf, "fetch_diff", lambda r, n: "+x\n" * 200)
    assert_blocked(pipeline.review_pr(REPO, 7, call=PASS), env)


@pytest.mark.parametrize("answer", [
    "not json at all",
    json.dumps({"feedback": "no fulfilled key"}),
    json.dumps({"fulfilled": "true", "feedback": "string true"}),
    json.dumps({"fulfilled": 1, "feedback": "int"}),
    json.dumps({"fulfilled": False, "feedback": "- AC2 missing"}),
    json.dumps([True]),
])
def test_bad_or_negative_llm_answers_block(env, answer):
    res = pipeline.review_pr(REPO, 7, call=llm(answer))
    assert_blocked(res, env)


def test_llm_exception_blocks(env):
    def boom(system, user):
        raise RuntimeError("quota exceeded")
    assert_blocked(pipeline.review_pr(REPO, 7, call=boom), env)


def test_fulfilled_false_comment_has_feedback(env):
    res = pipeline.review_pr(REPO, 7, call=llm(json.dumps({"fulfilled": False, "feedback": "- AC2 missing"})))
    body = [j for m, p, j in env if p.endswith("/comments")][0]["body"]
    assert "AC2 missing" in body


def test_fetch_pr_failure_takes_no_action(env, monkeypatch):
    def boom(r, n):
        raise cf.GitHubError("GitHub GET -> 401: Bad credentials")
    monkeypatch.setattr(cf, "fetch_pr", boom)
    res = pipeline.review_pr(REPO, 7, call=PASS)
    assert res["decision"] == "BLOCK" and res["actions"] == [] and env == []


def test_dry_run_no_http(env, monkeypatch):
    def no_gh(*a, **k):
        raise AssertionError("gh called in dry run")
    monkeypatch.setattr(cf, "gh", no_gh)
    res = pipeline.review_pr(REPO, 7, dry_run=True, call=PASS)
    assert res["decision"] == "MERGE"
    assert res["actions"] and all(a.startswith("[DRY-RUN]") for a in res["actions"])
    res = pipeline.review_pr(REPO, 7, dry_run=True, call=llm("garbage"))
    assert res["decision"] == "BLOCK"
    assert all(a.startswith("[DRY-RUN]") for a in res["actions"])


def test_executor_never_merges_without_bool_true(env):
    for v in [None, "true", 1, False]:
        executor.act(REPO, PR, {"fulfilled": v, "feedback": "", "error": None, "reason": "r"}, False)
    executor.act(REPO, PR, {"fulfilled": True, "feedback": "", "error": "boom", "reason": "r"}, False)
    assert not any(m == "PUT" for m, _, _ in env)


def test_stage_logs_printed(env, capsys):
    pipeline.review_pr(REPO, 7, dry_run=True, call=PASS)
    out = capsys.readouterr().out
    for tag in ("[1/6 webhook]", "[2/6 story]", "[3/6 code]", "[4/6 llm]", "[5/6 decision]", "[6/6 action]"):
        assert tag in out
