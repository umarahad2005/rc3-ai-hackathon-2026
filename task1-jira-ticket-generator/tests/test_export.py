"""Offline tests for export.py (no API): CSV round trip, parse_ac contract, JSON, console."""
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from export import (description_for, format_console, jira_priority, parse_ac,  # noqa: E402
                    to_csv, to_json)
from test_tickets import FACTS, build  # noqa: E402


def test_parse_ac_basic():
    d = "desc\n\nh3. Acceptance Criteria\n* one\n* two\n\nh3. Source\n* not ac"
    assert parse_ac(d) == ["one", "two"]
    assert parse_ac("no heading here") == []


def test_csv_round_trip(tmp_path):
    result = build()
    path = tmp_path / "tickets_jira.csv"
    to_csv(str(path), result["tickets"])
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert b"\r\r\n" not in raw
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == ["Summary", "Issue Type", "Description", "Priority", "Labels"]
        rows = list(reader)
    assert len(rows) == len(result["tickets"])
    for row, t in zip(rows, result["tickets"]):
        assert row["Labels"] == t["ticket_id"]
        assert row["Summary"] == t["title"]
        assert row["Issue Type"] == t["type"]
        if t["type"] == "Epic":
            assert "h3. Acceptance Criteria" in row["Description"]
            assert "Not applicable (epic) - see child tickets " + ", ".join(t["children"]) \
                in row["Description"]
            assert parse_ac(row["Description"]) == []
        else:
            assert parse_ac(row["Description"]) == [c["text"] for c in t["acceptance_criteria"]]
            assert parse_ac(row["Description"])  # every fixture task has criteria


def test_csv_ids_unique_sequential_and_priority(tmp_path):
    result = build()
    path = tmp_path / "t.csv"
    to_csv(str(path), result["tickets"])
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    labels = [r["Labels"] for r in rows]
    assert labels == [f"TASK-{i:03d}" for i in range(1, len(rows) + 1)]
    pri = {r["Labels"]: r["Priority"] for r in rows}
    assert pri["TASK-004"] == "High"
    assert pri["TASK-002"] == ""   # Not specified -> blank
    assert pri["TASK-001"] == ""   # epic


def test_jira_priority():
    assert jira_priority("Not specified") == ""
    assert jira_priority(None) == ""
    assert jira_priority("high") == "High"
    assert jira_priority("High priority") == "High"
    assert jira_priority("Low") == "Low"
    assert jira_priority("Highest") == "Highest"
    assert jira_priority("Medium") == "Medium"
    assert jira_priority("important") == ""


def test_description_template_sections():
    by = {t["ticket_id"]: t for t in build()["tickets"]}
    d = description_for(by["TASK-002"])
    assert "h3. Dependencies\nNone stated in brief" in d
    assert "h3. Open Questions\nNone" in d
    assert '{quote}S1: "Staff create classes with a name' in d
    assert ("Status: Ready | Parent: TASK-001 | Priority: Not specified | "
            "Estimate: Not specified | Deadline: Not specified") in d
    d4 = description_for(by["TASK-004"])
    assert "h3. Dependencies\nTASK-002" in d4
    assert "* [Q-003] What is the estimate for booking?" in d4


def test_ac_with_newline_and_no_ac():
    t = dict(build()["tickets"][1])
    t["acceptance_criteria"] = [{"text": "line one\nline two", "quote": "x"}]
    assert parse_ac(description_for(t)) == ["line one line two"]
    t["acceptance_criteria"] = []
    assert parse_ac(description_for(t)) == []


def test_to_json(tmp_path):
    result = build()
    p = tmp_path / "tickets.json"
    meta = {"brief_file": "briefs/clear.txt", "model": "gemini-2.5-flash",
            "generated_at": "2026-11-05T00:00:00"}
    rej = [{"stage": "understand", "item": {"id": "F9"}, "reason": "quote not in brief"}]
    to_json(str(p), meta, result, rej, ["WARNING x"])
    data = json.loads(p.read_text(encoding="utf-8"))
    for k in ("brief_file", "model", "generated_at", "tickets", "general_questions",
              "rejected", "lint_warnings"):
        assert k in data
    assert data["tickets"] == result["tickets"]
    assert data["rejected"] == rej


def test_format_console_full():
    result = build()
    rej = [{"stage": "understand", "item": {"id": "F9", "quote": "invented"},
            "reason": "quote not in brief"}]
    text = format_console(result, FACTS, rej, ["WARNING invented term: refund in TASK-004"])
    for t in result["tickets"]:
        assert t["ticket_id"] in text and t["title"] in text
        for c in t["acceptance_criteria"]:
            assert f'- {c["text"]}   <- "{c["quote"]}"' in text
    assert "Acceptance Criteria: Not applicable (epic) - see child tickets TASK-002" in text
    for q in result["questions"]:
        assert q["question"] in text
    assert "[scope_gap]" in text and "[missing]" in text
    assert "quote not in brief" in text
    assert "WARNING invented term: refund in TASK-004" in text
    assert "Facts: 3" in text
    assert "Rejected items: 1" in text
    assert "Ready:" in text and "Needs clarification:" in text


def test_console_contradiction_shows_both_quotes():
    result = {"tickets": [], "general_questions": [], "questions": [
        {"id": "Q-001", "category": "contradiction", "question": "Which applies for v1?",
         "quote": "App Store and Google Play", "quote_b": "web only for the first version",
         "linked_tickets": []}]}
    text = format_console(result, [], [], [])
    assert 'quote A: "App Store and Google Play"' in text
    assert 'quote B: "web only for the first version"' in text
