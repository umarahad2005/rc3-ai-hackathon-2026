"""Offline tests for the fixes made after the reviewer findings (no API calls)."""
import pytest

from tests.test_verify import CLEAR, CLEAR_S, VAGUE, VAGUE_S, FACTS, _task
from tickets import build_tickets
from verify import (check_questions, content_word_lint, filter_breakdown, invention_lint,
                    missing_info_scan, sanitize_descriptions, split_sentences)


def _bd(*tasks, epic_quote="group fitness classes"):
    return {"epics": [{"local_id": "E1", "title": "E", "description": "", "quote": epic_quote,
                       "tasks": list(tasks)}]}


# ---------------------------------------------------------------- value must be in its quote

def test_invented_values_on_real_quotes_dropped_with_question():
    t = _task("E1.T1", "Create class",
              priority={"value": "Highest", "quote": "The printable list is low priority"},
              deadline={"value": "1 January 2026", "quote": "The app must launch on 15 March 2027"},
              estimate={"value": "2 weeks", "quote": "Members can book a class up to 7 days before it starts"})
    bd, new_q, rej = filter_breakdown(_bd(t), CLEAR, FACTS, [])
    task = bd["epics"][0]["tasks"][0]
    for name in ("priority", "estimate", "deadline"):
        assert task[name] == {"value": None, "quote": None}
    assert [r["reason"] for r in rej].count("value not supported by quote") == 3
    texts = [q["question"] for q in new_q]
    assert "What is the priority for 'Create class'?" in texts
    assert set(task["blocked_by_question_ids"]) == {q["id"] for q in new_q}


def test_supported_priority_normalised_to_level_word():
    t = _task("E1.T1", "Book", priority={"value": "high priority",
                                         "quote": "Booking and cancellation are high priority"})
    bd, _, rej = filter_breakdown(_bd(t), CLEAR, FACTS, [])
    assert bd["epics"][0]["tasks"][0]["priority"]["value"] == "High"
    assert rej == []


def test_dropped_deadline_links_existing_deadline_question():
    qs = [{"id": "Q1", "category": "vague", "question": "What is the target live date?",
           "quote": "We need this live as soon as possible", "quote_b": None,
           "related_fact_ids": [], "source": "llm"}]
    facts = [{"id": "F1", "category": "feature", "text": "", "quote": "to order groceries"}]
    t = _task("E1.T1", "Order", source_fact_ids=["F1"],
              acceptance_criteria=[{"text": "Customers order groceries", "quote": "to order groceries"}],
              deadline={"value": "ASAP", "quote": "We need this live as soon as possible"})
    bd, new_q, _ = filter_breakdown(_bd(t, epic_quote="to order groceries"), VAGUE, facts, qs)
    assert new_q == []
    assert bd["epics"][0]["tasks"][0]["blocked_by_question_ids"] == ["Q1"]


# ---------------------------------------------------------------- malformed LLM lists

def test_non_string_list_elements_do_not_crash():
    t = _task("E1.T1", "Create class", source_fact_ids=["F1", ["F2"], {"x": 1}],
              blocked_by_question_ids=[["Q1"], {"a": 1}, "Q1"],
              dependencies=[{"local_id": ["E1.T2"], "quote": "x"}, ["E1.T2"]])
    t2 = _task("E1.T2", "Other", blocked_by_question_ids="Q1", dependencies="E1.T1")
    bd, _, rej = filter_breakdown(_bd(t, t2), CLEAR, FACTS, [])
    tasks = bd["epics"][0]["tasks"]
    assert tasks[0]["source_fact_ids"] == ["F1"]
    assert all(isinstance(x, str) for x in tasks[0]["blocked_by_question_ids"])
    qs, _ = check_questions({"questions": [{"id": "Q1", "category": "missing", "question": "Who?",
                                            "quote": None, "related_fact_ids": [["F1"], "F1"]}]},
                            CLEAR, CLEAR_S, FACTS)
    assert qs[0]["related_fact_ids"] == ["F1"]


def test_dependency_on_epic_rejected():
    t = _task("E1.T1", "Create class", dependencies=[{"local_id": "E1", "quote": "Staff create classes"}])
    bd, _, rej = filter_breakdown(_bd(t), CLEAR, FACTS, [])
    assert bd["epics"][0]["tasks"][0]["dependencies"] == []
    assert any("epic" in r["reason"] for r in rej)


# ---------------------------------------------------------------- question links

def test_unrelated_llm_link_dropped_but_own_quote_kept():
    qs = [{"id": "Q1", "category": "scope_gap", "question": "How is the membership number used?",
           "quote": "Members identify themselves with their membership number", "quote_b": None,
           "related_fact_ids": [], "source": "llm"},
          {"id": "Q2", "category": "scope_gap", "question": "Which details are on a class?",
           "quote": "Staff create classes with a name", "quote_b": None,
           "related_fact_ids": [], "source": "llm"}]
    t = _task("E1.T1", "Create class", blocked_by_question_ids=["Q1", "Q2"])
    bd, _, rej = filter_breakdown(_bd(t), CLEAR, FACTS, qs)
    assert bd["epics"][0]["tasks"][0]["blocked_by_question_ids"] == ["Q2"]
    assert any(r["item"].get("blocked_by_dropped") == ["Q1"] for r in rej if isinstance(r["item"], dict))


def test_priority_template_when_only_feature_question_mentions_priority():
    facts = [{"id": "F1", "category": "feature", "text": "", "quote": "Delivery slots are important to us."}]
    qs = [{"id": "Q1", "category": "vague", "question": "What does important mean for delivery slots "
           "in terms of their priority?", "quote": "Delivery slots are important to us.",
           "related_fact_ids": ["F1"]}]
    new = missing_info_scan(facts, qs)
    assert any("highest priority" in q["question"] for q in new)


def test_priority_template_linked_to_tasks_with_null_priority():
    facts = [{"id": "F1", "category": "feature", "text": "", "quote": "to order groceries"}]
    qs = missing_info_scan(facts, [])
    pq = next(q["id"] for q in qs if "priority" in q["question"])
    t = _task("E1.T1", "Order", source_fact_ids=["F1"],
              acceptance_criteria=[{"text": "Customers order groceries", "quote": "to order groceries"}])
    bd, _, _ = filter_breakdown(_bd(t, epic_quote="to order groceries"), VAGUE, facts, qs)
    assert pq in bd["epics"][0]["tasks"][0]["blocked_by_question_ids"]


def test_related_fact_question_only_on_task_whose_quote_matches():
    sents = split_sentences(VAGUE)
    facts = [{"id": "F1", "category": "feature", "text": "",
              "quote": "Customers browse products, add them to a basket and pay online."}]
    qs = [{"id": "Q1", "category": "scope_gap", "question": "Which payment methods?", "quote": "pay online",
           "quote_b": None, "related_fact_ids": ["F1"], "source": "llm"}]

    def task(lid, title, quote):
        return {"local_id": lid, "type": "Story", "title": title, "description": "",
                "source_fact_ids": ["F1"], "acceptance_criteria": [{"text": title, "quote": quote}],
                "dependencies": [], "blocked_by_question_ids": []}
    bd = {"epics": [{"local_id": "E1", "title": "Shop", "quote": None, "tasks": [
        task("E1.T1", "Browse products", "Customers browse products"),
        task("E1.T2", "Pay online", "pay online")]}]}
    r = build_tickets(bd, facts, qs, sents)
    by = {t["title"]: t for t in r["tickets"]}
    assert by["Browse products"]["open_questions"] == []
    assert [q["id"] for q in by["Pay online"]["open_questions"]] == ["Q-001"]


# ---------------------------------------------------------------- tickets fields

def test_source_reference_spanning_two_sentences_keeps_prefix():
    facts = [{"id": "F1", "category": "feature", "text": "",
              "quote": "before the class starts. Cancelling frees the place"}]
    bd = {"epics": [{"local_id": "E1", "title": "C", "quote": None, "tasks": [
        {"local_id": "E1.T1", "type": "Story", "title": "Cancel", "description": "",
         "source_fact_ids": ["F1"], "acceptance_criteria": [], "dependencies": [],
         "blocked_by_question_ids": []}]}]}
    r = build_tickets(bd, facts, [], CLEAR_S)
    ref = r["tickets"][1]["source_reference"]
    assert ref.startswith("S9-S10: ")


def test_epic_deadline_when_all_children_share_it():
    facts = [{"id": "F1", "category": "feature", "text": "", "quote": "Staff create classes"}]
    task = {"local_id": "E1.T1", "type": "Story", "title": "Create", "description": "",
            "source_fact_ids": ["F1"], "acceptance_criteria": [], "dependencies": [],
            "deadline": {"value": "15 March 2027", "quote": "launch on 15 March 2027"},
            "blocked_by_question_ids": []}
    r = build_tickets({"epics": [{"local_id": "E1", "title": "E", "quote": None,
                                  "tasks": [task, dict(task, local_id="E1.T2")]}]}, facts, [], CLEAR_S)
    assert r["tickets"][0]["deadline"] == "15 March 2027"


# ---------------------------------------------------------------- lints

def test_invention_lint_catches_inflections():
    tk = [{"ticket_id": "TASK-001", "title": "", "description": "Orders are refunded and invoicing runs",
           "acceptance_criteria": []}]
    w = invention_lint(tk, CLEAR)
    assert "WARNING invented term: refund in TASK-001" in w
    assert "WARNING invented term: invoice in TASK-001" in w


def test_content_word_lint_checks_title_and_description():
    tk = [{"ticket_id": "TASK-008", "title": "Order Management System Integration",
           "description": "Implement sync with ORMS", "acceptance_criteria": []}]
    w = content_word_lint(tk, VAGUE)
    assert "WARNING unsourced word 'management' in title of TASK-008" in w
    assert "WARNING unsourced word 'system' in title of TASK-008" in w
    assert not any("description of TASK-008" in x for x in w)   # implement = generic, sync/orms in brief


def test_sanitize_replaces_invented_epic_description():
    tk = [{"ticket_id": "TASK-001", "type": "Epic", "title": "Booking", "children": ["TASK-002"],
           "description": "Booking and cancelling, including related notifications."},
          {"ticket_id": "TASK-002", "type": "Story", "title": "Book a class", "children": [],
           "description": "Members book", "source_reference": 'S6: "Members can book a class"'}]
    rej = sanitize_descriptions(tk, CLEAR)
    assert tk[0]["description"] == "Covers: Book a class."
    assert len(rej) == 1 and rej[0]["stage"] == "lint"
    assert invention_lint(tk, CLEAR) == []


# ---------------------------------------------------------------- sentences, llm, cli

def test_heading_line_not_merged_into_next_sentence():
    s = split_sentences("Mobile app for customers\nWe want web only.")
    assert [x["text"] for x in s] == ["Mobile app for customers", "We want web only."]
    # a long wrapped line followed by a capitalised acronym is still one sentence
    assert len(split_sentences("Customers pay online. Orders should sync with our\nORMS so the "
                               "warehouse sees them.")) == 2


def test_daily_quota_is_not_retried():
    from llm import _is_daily_quota
    assert _is_daily_quota(Exception("429 RESOURCE_EXHAUSTED quotaId GenerateRequestsPerDayPerProjectPerModel-FreeTier"))
    assert not _is_daily_quota(Exception("429 RESOURCE_EXHAUSTED per minute"))


def test_usage_error_exits_1():
    import main
    with pytest.raises(SystemExit) as e:
        main.main([])
    assert e.value.code == 1


def test_llm_deadline_question_wording_suppresses_template():
    facts = [{"id": "F1", "category": "constraint", "text": "", "quote": "We need this live as soon as possible"}]
    qs = [{"id": "Q1", "category": "vague", "question": "What is the specific target date for the live launch?",
           "quote": "We need this live as soon as possible", "related_fact_ids": ["F1"]}]
    assert not any("deadline" in q["question"] for q in missing_info_scan(facts, qs))


def test_failed_run_keeps_previous_good_exports(tmp_path, monkeypatch):
    """D30: a 503 used to delete the last good tickets.json / CSV and overwrite run.log."""
    import llm
    import main
    brief = tmp_path / "b.txt"
    brief.write_text("Users should be able to pay online.", encoding="utf-8")
    out = tmp_path / "out"
    out.mkdir()
    for name, text in (("tickets.json", "GOOD"), ("tickets_jira.csv", "GOOD"), ("run.log", "GOOD")):
        (out / name).write_text(text, encoding="utf-8")

    def boom(*a, **k):
        raise llm.StageError("503 UNAVAILABLE")
    monkeypatch.setenv("GEMINI_API_KEY", "dummy")
    monkeypatch.setattr(llm, "call_json", boom)
    with pytest.raises(SystemExit) as e:
        main.run(str(brief), str(out), "m")
    assert e.value.code == 3
    for name in ("tickets.json", "tickets_jira.csv", "run.log"):
        assert (out / name).read_text(encoding="utf-8") == "GOOD"
    assert "503 UNAVAILABLE" in (out / "failed_run.log").read_text(encoding="utf-8")
    assert not list(out.glob("*.tmp"))


def test_priority_must_name_the_task():
    """D31: 'Booking and cancellation are high priority.' must not make an unrelated
    'Identify as a member' task High; it must still apply to booking / cancelling."""
    from verify import priority_names_task
    pq = "Booking and cancellation are high priority."
    assert not priority_names_task(pq, "Identify as a member",
                                   ["Members identify themselves with their membership number.", pq])
    assert priority_names_task(pq, "Book a class as a member",
                               ["Members can book a class up to 7 days before it starts."])
    assert priority_names_task(pq, "Cancel a booking as a member", [])
    assert priority_names_task("The printable list is low priority.",
                               "View and print booked members list as staff", [])
