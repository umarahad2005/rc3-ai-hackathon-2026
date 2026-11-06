import csv

import pytest

import code_fetcher
import story_fetcher
from story_fetcher import TicketError

EPIC_DESC = ("This epic covers staff classes.\n\nh3. Acceptance Criteria\n"
             "Not applicable (epic) - see child tickets TASK-002, TASK-003\n\n"
             "h3. Source\n{quote}S5: \"Staff create classes.\"{quote}")
STORY_DESC = ("Staff must view and print member lists.\n\nh3. Acceptance Criteria\n"
              "* Staff can view the list of members booked into each class.\n"
              "* Staff can print the list of members booked into each class.\n\n"
              "h3. Source\n{quote}S11: \"Staff can view...\"{quote}\n\n"
              "h3. Open Questions\n* [Q-001] How do staff log in?")

ENV = ["JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN", "TICKETS_CSV", "GITHUB_TOKEN"]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for k in ENV:
        monkeypatch.delenv(k, raising=False)


@pytest.fixture
def csv_path(tmp_path):
    p = tmp_path / "tickets_jira.csv"
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, quoting=csv.QUOTE_ALL)
        w.writerow(["Summary", "Issue Type", "Description", "Priority", "Labels"])
        w.writerow(["Staff Class Management", "Epic", EPIC_DESC, "", "TASK-001"])
        w.writerow(["View and print member lists", "Story", STORY_DESC, "Low", "TASK-003"])
    return str(p)


class Resp:
    def __init__(self, status=200, json_data=None, text=""):
        self.status_code, self._j, self.text = status, json_data, text

    def json(self):
        if self._j is None:
            raise ValueError("no json")
        return self._j


def test_extract_ticket_id_branch_first():
    assert story_fetcher.extract_ticket_id("feature/TASK-003-print", "TASK-009 title") == "TASK-003"


def test_extract_ticket_id_title_fallback():
    assert story_fetcher.extract_ticket_id("feature/print", "PROJ-12: print lists") == "PROJ-12"


def test_extract_ticket_id_none():
    assert story_fetcher.extract_ticket_id("main", "no ticket here") is None
    assert story_fetcher.extract_ticket_id(None, None) is None


def test_parse_ac_story():
    assert story_fetcher.parse_ac(STORY_DESC) == [
        "Staff can view the list of members booked into each class.",
        "Staff can print the list of members booked into each class.",
    ]


def test_parse_ac_epic_is_empty():
    assert story_fetcher.parse_ac(EPIC_DESC) == []
    assert story_fetcher.parse_ac("") == []


def test_fetch_ticket_csv(monkeypatch, csv_path):
    monkeypatch.setenv("TICKETS_CSV", csv_path)
    t = story_fetcher.fetch_ticket("TASK-003")
    assert t["source"] == "csv" and t["id"] == "TASK-003"
    assert t["title"] == "View and print member lists"
    assert len(t["acceptance_criteria"]) == 2
    assert story_fetcher.fetch_ticket("TASK-001")["acceptance_criteria"] == []


def test_fetch_ticket_csv_not_found(monkeypatch, csv_path):
    monkeypatch.setenv("TICKETS_CSV", csv_path)
    with pytest.raises(TicketError):
        story_fetcher.fetch_ticket("TASK-999")


def test_fetch_ticket_no_source():
    with pytest.raises(TicketError):
        story_fetcher.fetch_ticket("TASK-003")


def test_fetch_ticket_jira(monkeypatch):
    monkeypatch.setenv("JIRA_BASE_URL", "https://x.atlassian.net/")
    monkeypatch.setenv("JIRA_EMAIL", "a@b.c")
    monkeypatch.setenv("JIRA_API_TOKEN", "tok")
    seen = {}

    def fake_get(url, **kw):
        seen["url"] = url
        seen.update(kw)
        return Resp(200, {"fields": {"summary": "Print lists", "description": STORY_DESC}})

    monkeypatch.setattr(story_fetcher.requests, "get", fake_get)
    t = story_fetcher.fetch_ticket("TASK-003")
    assert seen["url"] == "https://x.atlassian.net/rest/api/2/issue/TASK-003"
    assert seen["params"] == {"fields": "summary,description,labels"}
    assert seen["auth"] == ("a@b.c", "tok") and seen["timeout"] == 15
    assert t["source"] == "jira" and len(t["acceptance_criteria"]) == 2


def test_fetch_ticket_jira_http_error(monkeypatch):
    for k, v in [("JIRA_BASE_URL", "https://x"), ("JIRA_EMAIL", "e"), ("JIRA_API_TOKEN", "t")]:
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(story_fetcher.requests, "get", lambda url, **kw: Resp(404, {}))
    with pytest.raises(TicketError):
        story_fetcher.fetch_ticket("TASK-003")


def test_fetch_diff_accept_header(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghtok")
    seen = {}

    def fake_request(method, url, headers=None, **kw):
        seen.update(method=method, url=url, headers=headers)
        return Resp(200, text="diff --git a/x b/x\n")

    monkeypatch.setattr(code_fetcher.requests, "request", fake_request)
    assert code_fetcher.fetch_diff("o/r", 7).startswith("diff --git")
    assert seen["method"] == "GET" and seen["url"] == "https://api.github.com/repos/o/r/pulls/7"
    assert seen["headers"]["Accept"] == "application/vnd.github.diff"
    assert seen["headers"]["Authorization"] == "Bearer ghtok"


def test_fetch_pr(monkeypatch):
    data = {"number": 7, "title": "TASK-003 print", "head": {"ref": "feat/TASK-003", "sha": "abc"},
            "base": {"ref": "main"}, "state": "open", "merged": False}
    monkeypatch.setattr(code_fetcher.requests, "request", lambda m, u, **kw: Resp(200, data))
    pr = code_fetcher.fetch_pr("o/r", 7)
    assert pr == {"number": 7, "title": "TASK-003 print", "head_ref": "feat/TASK-003",
                  "head_sha": "abc", "base_ref": "main", "state": "open", "merged": False}


def test_gh_raises_on_404(monkeypatch):
    monkeypatch.setattr(code_fetcher.requests, "request",
                        lambda m, u, **kw: Resp(404, {"message": "Not Found"}))
    with pytest.raises(code_fetcher.GitHubError) as ei:
        code_fetcher.gh("GET", "/repos/o/r/pulls/1")
    assert "404" in str(ei.value) and "Not Found" in str(ei.value)
