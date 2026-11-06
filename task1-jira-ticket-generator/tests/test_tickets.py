"""Offline tests for tickets.build_tickets (no API). Fixtures are built by hand."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tickets import build_tickets  # noqa: E402

BRIEF_SENTENCES = [
    {"sid": "S1", "text": "Staff create classes with a name, instructor, start time and capacity."},
    {"sid": "S2", "text": "Members can book a class up to 7 days before it starts."},
    {"sid": "S3", "text": "Members can only book classes that staff have already created."},
    {"sid": "S4", "text": "Booking and cancellation are high priority."},
    {"sid": "S5", "text": "Members receive a booking confirmation after they book."},
]

FACTS = [
    {"id": "F1", "category": "feature", "text": "staff create classes",
     "quote": "Staff create classes with a name, instructor, start time and capacity"},
    {"id": "F2", "category": "feature", "text": "members book",
     "quote": "Members can book a class up to 7 days before it starts"},
    {"id": "F3", "category": "feature", "text": "confirmation",
     "quote": "Members receive a booking confirmation"},
]

QUESTIONS = [
    {"id": "Q1", "category": "scope_gap", "question": "Through which channel is the confirmation sent?",
     "quote": "Members receive a booking confirmation", "quote_b": None,
     "related_fact_ids": ["F3"], "source": "llm"},
    {"id": "Q2", "category": "missing", "question": "Does the system need to integrate with any existing systems?",
     "quote": None, "quote_b": None, "related_fact_ids": [], "source": "template"},
    {"id": "Q3", "category": "missing", "question": "What is the estimate for booking?",
     "quote": None, "quote_b": None, "related_fact_ids": [], "source": "breakdown"},
]


def make_breakdown():
    return {"epics": [
        {"local_id": "E1", "title": "Class management", "description": "Staff manage classes",
         "quote": "Staff create classes",
         "tasks": [
             {"local_id": "E1.T1", "type": "Story", "title": "Create classes",
              "description": "Staff create classes", "source_fact_ids": ["F1"],
              "acceptance_criteria": [{"text": "Staff can create a class with a name",
                                       "quote": "Staff create classes with a name"}],
              "dependencies": [], "priority": {"value": None, "quote": None},
              "estimate": {"value": None, "quote": None}, "deadline": {"value": None, "quote": None},
              "blocked_by_question_ids": []}]},
        {"local_id": "E2", "title": "Booking", "description": "Members book classes",
         "quote": "this quote is not in the brief at all",
         "tasks": [
             {"local_id": "E2.T1", "type": "Story", "title": "Book a class",
              "description": "Members book", "source_fact_ids": ["F2", "F99"],
              "acceptance_criteria": [{"text": "Members can book up to 7 days before",
                                       "quote": "Members can book a class up to 7 days before it starts"},
                                      {"text": "Only created classes can be booked",
                                       "quote": "Members can only book classes that staff have already created"}],
              "dependencies": [{"local_id": "E1.T1", "quote": "Members can only book classes that staff have already created"},
                               {"local_id": "E9.T9", "quote": "x"}],
              "priority": {"value": "High", "quote": "Booking and cancellation are high priority"},
              "estimate": {"value": None, "quote": None}, "deadline": {"value": None, "quote": None},
              "blocked_by_question_ids": ["Q3", "Q404"]},
             {"local_id": "E2.T2", "type": "Bogus", "title": "Send booking confirmation",
              "description": "Members receive a confirmation", "source_fact_ids": ["F3"],
              "acceptance_criteria": [{"text": "Members receive a booking confirmation after they book",
                                       "quote": "Members receive a booking confirmation after they book"}],
              "dependencies": [{"local_id": "E2.T1", "quote": "after they book"}],
              "priority": {"value": None, "quote": None},
              "estimate": {"value": None, "quote": None}, "deadline": {"value": None, "quote": None},
              "blocked_by_question_ids": []}]},
    ]}


def build():
    return build_tickets(make_breakdown(), FACTS, QUESTIONS, BRIEF_SENTENCES)


KEYS = {"ticket_id", "title", "type", "parent", "children", "description", "acceptance_criteria",
        "source_reference", "dependencies", "open_questions", "priority", "estimate", "deadline",
        "status"}


def test_ids_sequential_unique_epic_then_tasks():
    t = build()["tickets"]
    ids = [x["ticket_id"] for x in t]
    assert ids == [f"TASK-{i:03d}" for i in range(1, 6)]
    assert [x["type"] for x in t] == ["Epic", "Story", "Epic", "Story", "Task"]
    assert t[0]["children"] == ["TASK-002"] and t[2]["children"] == ["TASK-004", "TASK-005"]
    assert t[1]["parent"] == "TASK-001" and t[3]["parent"] == "TASK-003"
    assert t[0]["parent"] is None


def test_same_keys_on_every_ticket():
    for x in build()["tickets"]:
        assert set(x) == KEYS


def test_dependencies_remapped_no_dangling():
    t = build()["tickets"]
    ids = {x["ticket_id"] for x in t}
    by = {x["ticket_id"]: x for x in t}
    assert by["TASK-004"]["dependencies"] == ["TASK-002"]  # unknown E9.T9 dropped
    assert by["TASK-005"]["dependencies"] == ["TASK-004"]
    for x in t:
        assert set(x["dependencies"]) <= ids


def test_question_links_union_and_renumber():
    r = build()
    by = {x["ticket_id"]: x for x in r["tickets"]}
    assert [q["id"] for q in r["questions"]] == ["Q-001", "Q-002", "Q-003"]
    # blocked_by Q3 -> Q-003; unknown Q404 ignored
    assert [q["id"] for q in by["TASK-004"]["open_questions"]] == ["Q-003"]
    # related_fact_ids overlap F3 -> Q-001
    assert [q["id"] for q in by["TASK-005"]["open_questions"]] == ["Q-001"]
    for q in by["TASK-005"]["open_questions"]:
        assert {"id", "category", "question"} <= set(q)


def test_unlinked_questions_on_every_epic_and_general():
    r = build()
    by = {x["ticket_id"]: x for x in r["tickets"]}
    assert [q["id"] for q in r["general_questions"]] == ["Q-002"]
    for eid in ("TASK-001", "TASK-003"):
        assert [q["id"] for q in by[eid]["open_questions"]] == ["Q-002"]
    q2 = next(q for q in r["questions"] if q["id"] == "Q-002")
    assert q2["linked_tickets"] == ["TASK-001", "TASK-003"]


def test_no_lost_questions():
    r = build()
    seen = set()
    for x in r["tickets"]:
        seen |= {q["id"] for q in x["open_questions"]}
    seen |= {q["id"] for q in r["general_questions"]}
    assert seen == {q["id"] for q in r["questions"]}
    assert len(r["questions"]) == len(QUESTIONS)
    for q in r["questions"]:
        assert q["linked_tickets"]


def test_status_logic_and_epic_inheritance():
    r = build_tickets(make_breakdown(), FACTS, QUESTIONS[:1] + QUESTIONS[2:], BRIEF_SENTENCES)
    by = {x["ticket_id"]: x for x in r["tickets"]}
    assert r["general_questions"] == []
    assert by["TASK-002"]["status"] == "Ready"
    assert by["TASK-001"]["status"] == "Ready"          # no own questions, child Ready
    assert by["TASK-004"]["status"] == "Needs clarification"
    assert by["TASK-003"]["open_questions"] == []
    assert by["TASK-003"]["status"] == "Needs clarification"  # inherited from children


def test_epic_with_general_question_needs_clarification():
    by = {x["ticket_id"]: x for x in build()["tickets"]}
    assert by["TASK-001"]["status"] == "Needs clarification"


def test_defaults_and_values():
    by = {x["ticket_id"]: x for x in build()["tickets"]}
    assert by["TASK-004"]["priority"] == "High"
    assert by["TASK-004"]["estimate"] == "Not specified"
    assert by["TASK-004"]["deadline"] == "Not specified"
    for eid in ("TASK-001", "TASK-003"):
        e = by[eid]
        assert e["acceptance_criteria"] == []
        assert (e["priority"], e["estimate"], e["deadline"]) == ("Not specified",) * 3


def test_source_reference():
    by = {x["ticket_id"]: x for x in build()["tickets"]}
    assert by["TASK-002"]["source_reference"] == \
        'S1: "Staff create classes with a name, instructor, start time and capacity"'
    assert by["TASK-001"]["source_reference"] == 'S1: "Staff create classes"'
    # epic quote not verified -> first child's reference
    assert by["TASK-003"]["source_reference"] == by["TASK-004"]["source_reference"]
    assert by["TASK-004"]["source_reference"].startswith("S2: ")


def test_empty_breakdown():
    r = build_tickets({"epics": []}, FACTS, QUESTIONS, BRIEF_SENTENCES)
    assert r["tickets"] == []
    assert len(r["general_questions"]) == 3
