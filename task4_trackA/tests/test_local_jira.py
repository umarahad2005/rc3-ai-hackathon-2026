import json

import pytest

import story_fetcher as sf
from csv_to_jira_json import convert

DESC = "Close booking.\n\nh3. Acceptance Criteria\n* When a class reaches its capacity, booking closes\n\nh3. Source\nS5"


@pytest.fixture
def env(monkeypatch, tmp_path):
    for k in ("JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN", "TICKETS_CSV"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("JIRA_TICKETS_DIR", str(tmp_path))
    return tmp_path


def test_local_issue_file_v2(env):
    (env / "RC3-5.json").write_text(json.dumps({"key": "RC3-5", "fields": {"summary": "Cap", "description": DESC}}))
    t = sf.fetch_ticket("RC3-5")
    assert t["source"] == "jira-local" and t["acceptance_criteria"] == ["When a class reaches its capacity, booking closes"]


def test_local_search_export(env):
    (env / "export.json").write_text(json.dumps({"issues": [{"key": "RC3-1", "fields": {"summary": "x", "description": ""}},
                                                            {"key": "RC3-7", "fields": {"summary": "Cap", "description": DESC}}]}))
    assert sf.fetch_ticket("RC3-7")["title"] == "Cap"


def test_local_adf_v3_description(env):
    adf = {"type": "doc", "content": [
        {"type": "heading", "attrs": {"level": 3}, "content": [{"type": "text", "text": "Acceptance Criteria"}]},
        {"type": "bulletList", "content": [{"type": "listItem", "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "Shows Class full"}]}]}]}]}
    (env / "RC3-9.json").write_text(json.dumps({"key": "RC3-9", "fields": {"summary": "s", "description": adf}}))
    assert sf.fetch_ticket("RC3-9")["acceptance_criteria"] == ["Shows Class full"]


def test_local_missing_and_bad_json(env):
    with pytest.raises(sf.TicketError):
        sf.fetch_ticket("RC3-404")
    (env / "RC3-2.json").write_text("{not json")
    with pytest.raises(sf.TicketError):
        sf.fetch_ticket("RC3-2")


def test_csv_converter_roundtrip(env, tmp_path):
    csv_path = tmp_path / "t.csv"
    csv_path.write_text('"Summary","Issue Type","Description","Priority","Labels"\n'
                        f'"Cap","Story","{DESC}","High","TASK-004"\n', encoding="utf-8")
    convert(str(csv_path), str(env))
    t = sf.fetch_ticket("TASK-004")
    assert t["acceptance_criteria"] and t["source"] == "jira-local"
