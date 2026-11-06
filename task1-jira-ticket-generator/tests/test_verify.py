"""Offline tests for verify.py (no API calls). PLAN.md section 7, checks T1 and T2."""
from verify import (normalise, quote_ok, sentence_of, split_sentences, filter_facts,
                    check_questions, missing_info_scan, filter_breakdown, clean_ac_text,
                    invention_lint, content_word_lint)

CLEAR = """FitLane Gym - Class Booking Web App

FitLane Gym runs group fitness classes at one branch. We need a web application that works in
desktop and mobile browsers. It has two user groups: members and front-desk staff.

Staff create classes with a name, instructor, start time and capacity.
Members can book a class up to 7 days before it starts.
Members can only book classes that staff have already created.
When a class reaches its capacity, booking closes and members see the message "Class full".
Members can cancel a booking up to 2 hours before the class starts. Cancelling frees the place
for another member.
Staff can view the list of members booked into each class and print it.
Members receive a booking confirmation after they book.

Booking and cancellation are high priority. The printable list is low priority.
The app must launch on 15 March 2027.
Members identify themselves with their membership number.
"""

VAGUE = """Hi team,

We are a family-run grocery business and want to finally go digital. Customers will download
our new app from the App Store and Google Play to order groceries. The app must be fast,
modern and secure.

Customers browse products, add them to a basket and pay online. Orders should sync with our
ORMS so the warehouse sees them straight away. We would also like the loyalty scheme to work
like last time. Delivery slots are important to us.

Admins should get the usual reports every week.

For budget reasons we want web only for the first version.

We need this live as soon as possible.

Thanks,
Bilal
"""

CLEAR_S = split_sentences(CLEAR)
VAGUE_S = split_sentences(VAGUE)


# ------------------------------------------------------------------ T1: quote_ok / sentence_of

def test_exact_quote_passes():
    assert quote_ok("Members can book a class up to 7 days before it starts.", CLEAR)


def test_curly_quotes_pass():
    assert quote_ok("members see the message “Class full”", CLEAR)


def test_extra_whitespace_and_line_break_pass():
    # the brief breaks this sentence across a newline
    assert quote_ok("works in   desktop and\n mobile browsers", CLEAR)


def test_case_and_trailing_full_stop_ignored():
    assert quote_ok("THE APP MUST LAUNCH ON 15 MARCH 2027.", CLEAR)


def test_paraphrase_fails():
    assert not quote_ok("Members may reserve a class a week in advance", CLEAR)


def test_ellipsis_fails():
    assert not quote_ok("Members can book ... before it starts", CLEAR)
    assert not quote_ok("Members can book … before it starts", CLEAR)


def test_one_word_quote_fails():
    assert not quote_ok("booking", CLEAR)
    assert not quote_ok("", CLEAR)
    assert not quote_ok(None, CLEAR)


def test_normalise():
    assert normalise("  It’s  “OK” — fine.  ") == "it's \"ok\" - fine"


def test_split_sentences():
    texts = [s["text"] for s in CLEAR_S]
    assert CLEAR_S[0] == {"sid": "S1", "text": "FitLane Gym - Class Booking Web App"}
    assert "Members can book a class up to 7 days before it starts." in texts
    assert all(t.strip() for t in texts)
    assert [s["sid"] for s in CLEAR_S] == [f"S{i}" for i in range(1, len(CLEAR_S) + 1)]


def test_sentence_of_finds_right_sentence():
    sid = sentence_of("up to 7 days before it starts", CLEAR_S)
    sent = next(s for s in CLEAR_S if s["sid"] == sid)
    assert sent["text"] == "Members can book a class up to 7 days before it starts."
    assert sentence_of("we want web only", VAGUE_S) != sentence_of("App Store and Google Play", VAGUE_S)
    assert sentence_of("not in the brief at all", CLEAR_S) is None


# ------------------------------------------------------------------ Stage 2: filter_facts

def test_filter_facts_rejects_bad_quotes_and_renumbers():
    raw = {"facts": [
        {"id": "F1", "category": "user", "text": "members", "quote": "two user groups: members and front-desk staff"},
        {"id": "F1", "category": "deadline", "text": "launch", "quote": "The app must launch on 15 March 2027"},
        {"id": "F3", "category": "feature", "text": "waitlist", "quote": "Members join a waiting list when full"},
        {"id": "F4", "category": "feature", "text": "x", "quote": "booking"},
    ]}
    facts, rejected = filter_facts(raw, CLEAR)
    assert [f["id"] for f in facts] == ["F1", "F5"]
    assert len({f["id"] for f in facts}) == len(facts)
    assert len(rejected) == 2
    assert all(r["stage"] == "understand" for r in rejected)
    assert [r["reason"] for r in rejected] == ["quote not in brief", "quote too short (<8 chars)"]


def test_filter_facts_handles_garbage():
    facts, rejected = filter_facts({"facts": ["oops"]}, CLEAR)
    assert facts == [] and len(rejected) == 1
    assert filter_facts({}, CLEAR) == ([], [])


# ------------------------------------------------------------------ T2: contradictions

def _contra(qa, qb):
    return {"questions": [{"id": "Q1", "category": "contradiction", "question": "Which applies for v1?",
                           "quote": qa, "quote_b": qb, "related_fact_ids": []}]}


def test_valid_contradiction_kept():
    qs, rej = check_questions(_contra("App Store and Google Play", "we want web only for the first version"),
                              VAGUE, VAGUE_S, [])
    assert len(qs) == 1 and rej == []
    assert qs[0]["quote_b"] == "we want web only for the first version"


def test_contradiction_with_one_quote_rejected():
    qs, rej = check_questions(_contra("App Store and Google Play", None), VAGUE, VAGUE_S, [])
    assert qs == [] and len(rej) == 1


def test_contradiction_same_quote_twice_rejected():
    qs, rej = check_questions(_contra("we want web only", "we want web only"), VAGUE, VAGUE_S, [])
    assert qs == [] and rej[0]["reason"] == "contradiction quotes same sentence/nested"


def test_contradiction_nested_quote_rejected():
    qs, rej = check_questions(_contra("web only", "want web only"), VAGUE, VAGUE_S, [])
    assert qs == [] and rej[0]["reason"] == "contradiction quotes same sentence/nested"


def test_contradiction_same_sentence_rejected():
    qs, rej = check_questions(_contra("Customers browse products", "add them to a basket and pay online"), VAGUE, VAGUE_S, [])
    assert qs == [] and rej[0]["reason"] == "contradiction quotes same sentence/nested"


def test_check_questions_quotes_and_links():
    facts = [{"id": "F1", "category": "feature", "text": "t", "quote": "pay online"}]
    raw = {"questions": [
        {"id": "Q1", "category": "vague", "question": "What does 'fast' mean?", "quote": "The app must be fast",
         "quote_b": None, "related_fact_ids": ["F1", "F99"]},
        {"id": "Q2", "category": "vague", "question": "Invented?", "quote": "must load in 2 seconds",
         "quote_b": None, "related_fact_ids": []},
        {"id": "Q3", "category": "missing", "question": "Who are the admins?", "quote": None,
         "quote_b": None, "related_fact_ids": []},
        {"id": "Q3", "category": "vague", "question": "No quote", "quote": None,
         "quote_b": None, "related_fact_ids": []},
    ]}
    qs, rej = check_questions(raw, VAGUE, VAGUE_S, facts)
    assert [q["id"] for q in qs] == ["Q1", "Q3"]
    assert qs[0]["related_fact_ids"] == ["F1"]
    assert qs[0]["source"] == "llm"
    assert len(rej) == 2 and all(r["stage"] == "gaps" for r in rej)


# ------------------------------------------------------------------ missing_info_scan

def test_missing_info_scan_all_topics_when_no_facts():
    new = missing_info_scan([], [{"id": "Q4", "question": "x"}])
    texts = " ".join(q["question"] for q in new)
    assert len(new) == 5
    assert [q["id"] for q in new] == ["Q5", "Q6", "Q7", "Q8", "Q9"]
    for word in ("target users", "deadline", "platform", "integrate", "priority"):
        assert word in texts
    assert all(q["source"] == "template" and q["quote"] is None and q["category"] == "missing"
               and q["related_fact_ids"] == [] for q in new)


def test_missing_info_scan_clear_brief_only_integration():
    facts = [
        {"id": "F1", "category": "user", "text": "", "quote": "two user groups: members and front-desk staff"},
        {"id": "F2", "category": "constraint", "text": "", "quote": "works in\ndesktop and mobile browsers"},
        {"id": "F3", "category": "deadline", "text": "", "quote": "The app must launch on 15 March 2027"},
        {"id": "F4", "category": "priority", "text": "", "quote": "Booking and cancellation are high priority"},
    ]
    new = missing_info_scan(facts, [])
    assert len(new) == 1 and "integrate" in new[0]["question"]


def test_missing_info_scan_deadline_needs_digit_and_skips_asked_topics():
    facts = [{"id": "F1", "category": "deadline", "text": "", "quote": "We need this live as soon as possible"}]
    qs = [{"id": "Q1", "question": "Which platform applies for v1: App Store and Google Play, or web only?"}]
    texts = [q["question"] for q in missing_info_scan(facts, qs)]
    assert "What is the deadline or launch date?" in texts
    assert "Which platform(s) must be supported?" not in texts


# ------------------------------------------------------------------ Stage 4: filter_breakdown

FACTS = [
    {"id": "F1", "category": "feature", "text": "", "quote": "Staff create classes with a name, instructor, start time and capacity"},
    {"id": "F2", "category": "feature", "text": "", "quote": "Members can book a class up to 7 days before it starts"},
]
QUESTIONS = [{"id": "Q1", "category": "missing", "question": "Integrations?", "quote": None,
              "quote_b": None, "related_fact_ids": [], "source": "template"}]


def _task(lid, title, **kw):
    t = {"local_id": lid, "type": "Story", "title": title, "description": "d", "source_fact_ids": ["F1"],
         "acceptance_criteria": [{"text": "Staff can create a class", "quote": "Staff create classes"}],
         "dependencies": [], "priority": {"value": None, "quote": None},
         "estimate": {"value": None, "quote": None}, "deadline": {"value": None, "quote": None},
         "blocked_by_question_ids": []}
    t.update(kw)
    return t


def test_filter_breakdown_drops():
    raw = {"epics": [{"local_id": "E1", "title": "Classes", "description": "", "quote": "group fitness classes",
                      "tasks": [
        _task("E1.T1", "Create class"),
        _task("E1.T2", "Book class", source_fact_ids=["F2"],
              acceptance_criteria=[
                  {"text": "* Member can book\nup to 7 days ahead", "quote": "up to 7 days before it starts"},
                  {"text": "Refund issued", "quote": "refunds are issued"}],
              dependencies=[{"local_id": "E1.T1", "quote": "Members can only book classes that staff have already created"},
                            {"local_id": "E1.T3", "quote": "nonsense quote here"},
                            {"local_id": "E9", "quote": "x"}],
              priority={"value": "High", "quote": "Booking and cancellation are high priority"},
              estimate={"value": "3 days", "quote": "takes three days"},
              deadline={"value": "ASAP", "quote": "booking closes"},
              blocked_by_question_ids=["Q1", "Q77"]),
        _task("E1.T3", "Show list", acceptance_criteria=[{"text": "x", "quote": "bad quote not here"}]),
        _task("E1.T4", "Send SMS", source_fact_ids=["F42"]),
    ]}]}
    bd, new_q, rej = filter_breakdown(raw, CLEAR, FACTS, QUESTIONS)
    tasks = bd["epics"][0]["tasks"]
    assert [t["local_id"] for t in tasks] == ["E1.T1", "E1.T2", "E1.T3"]       # invented task gone
    book = tasks[1]
    assert book["acceptance_criteria"] == [{"text": "Member can book up to 7 days ahead",
                                            "quote": "up to 7 days before it starts"}]
    assert [d["local_id"] for d in book["dependencies"]] == ["E1.T1"]
    assert book["priority"]["value"] == "High"
    assert book["estimate"] == {"value": None, "quote": None}
    assert book["deadline"] == {"value": None, "quote": None}                # no digit
    # new questions: dropped estimate + deadline values, zero-AC for E1.T3,
    # dropped dependency E1.T2 -> E1.T3
    texts = [q["question"] for q in new_q]
    assert texts == ["What is the estimate for 'Book class'?",
                     "What is the deadline for 'Book class'?",
                     "What testable acceptance conditions apply to 'Show list'?",
                     "Does Book class depend on Show list?"]
    assert [q["id"] for q in new_q] == ["Q2", "Q3", "Q4", "Q5"]
    assert all(q["source"] == "breakdown" for q in new_q)
    # Q1 is a whole-brief template question (no quote): not about this task, so the link is
    # dropped (it stays a general question); Q77 is unknown.
    assert book["blocked_by_question_ids"] == ["Q2", "Q3", "Q5"]
    assert {"Q1", "Q77"}.isdisjoint(book["blocked_by_question_ids"])
    reasons = [r["reason"] for r in rej]
    assert "task has no verified source facts (invented)" in reasons
    assert "acceptance criterion quote not in brief" in reasons
    assert "estimate quote not in brief" in reasons
    assert "deadline quote has no digit (not a concrete date)" in reasons
    assert "dependency target unknown" in reasons


def test_filter_breakdown_keeps_deadline_with_digit():
    raw = {"epics": [{"local_id": "E1", "title": "E", "quote": "group fitness classes", "tasks": [
        _task("E1.T1", "Create class", deadline={"value": "15 March 2027",
                                                  "quote": "The app must launch on 15 March 2027"})]}]}
    bd, _, _ = filter_breakdown(raw, CLEAR, FACTS, QUESTIONS)
    assert bd["epics"][0]["tasks"][0]["deadline"]["value"] == "15 March 2027"


def test_clean_ac_text():
    assert clean_ac_text("h3. * Members see\n\"Class full\"") == 'Members see "Class full"'


# ------------------------------------------------------------------ lints

def test_invention_lint():
    tickets = [{"ticket_id": "TASK-004", "title": "Process refunds", "description": "Use Stripe",
                "acceptance_criteria": [{"text": "Page loads in 2 seconds", "quote": "x"}]},
               {"ticket_id": "TASK-005", "title": "Book a class in the web app", "description": "",
                "acceptance_criteria": []}]
    w = invention_lint(tickets, CLEAR)
    assert "WARNING invented term: refund in TASK-004" in w
    assert "WARNING invented term: stripe in TASK-004" in w
    assert any("2 seconds in TASK-004" in x for x in w)
    assert not any("TASK-005" in x for x in w)


def test_content_word_lint():
    tickets = [{"ticket_id": "TASK-004", "title": "", "description": "",
                "acceptance_criteria": [{"text": "Members receive refunds when cancelling",
                                         "quote": "Members can cancel a booking"}]}]
    w = content_word_lint(tickets, CLEAR)
    assert w == ["WARNING unsourced word 'refunds' in AC of TASK-004"]


# ------------------------------------------------------------------ defect fix: hard-wrapped lines

def test_wrapped_sentence_is_one_sentence():
    texts = [s["text"] for s in VAGUE_S]
    assert "The app must be fast, modern and secure." in texts
    assert "Customers will download our new app from the App Store and Google Play to order groceries." in texts
    assert sentence_of("fast,\nmodern and secure", VAGUE_S) is not None


def test_contradiction_quote_across_line_wrap_kept():
    qs, rej = check_questions(_contra("download our new app from the App Store and Google Play",
                                      "we want web only for the first version"), VAGUE, VAGUE_S, [])
    assert len(qs) == 1 and rej == []


# ------------------------------------------------------------------ defect fixes found in real runs

def test_example_answers_stripped_from_questions():
    raw = {"questions": [{"id": "Q1", "category": "scope_gap",
                          "question": "In what format (e.g., CSV, PDF, in-app dashboard) should the weekly reports be delivered?",
                          "quote": "the usual reports every week", "quote_b": None, "related_fact_ids": []}]}
    qs, rej = check_questions(raw, VAGUE, VAGUE_S, [])
    assert qs[0]["question"] == "In what format should the weekly reports be delivered?"
    assert "dashboard" not in qs[0]["question"]
    assert rej and "example" in rej[0]["reason"]


def _one_task_breakdown(**task_over):
    task = {"local_id": "E1.T1", "type": "Story", "title": "Order groceries", "description": "",
            "source_fact_ids": ["F1"], "acceptance_criteria": [], "dependencies": [],
            "priority": {"value": None, "quote": None}, "estimate": {"value": None, "quote": None},
            "deadline": {"value": None, "quote": None}, "blocked_by_question_ids": []}
    task.update(task_over)
    return {"epics": [{"local_id": "E1", "title": "Ordering", "description": "",
                       "quote": "to order groceries", "tasks": [task]}]}


def test_priority_without_priority_word_dropped():
    facts = [{"id": "F1", "category": "feature", "text": "", "quote": "to order groceries"}]
    bd, _, rej = filter_breakdown(_one_task_breakdown(
        priority={"value": "as soon as possible", "quote": "We need this live as soon as possible"}),
        VAGUE, facts, [])
    assert bd["epics"][0]["tasks"][0]["priority"] == {"value": None, "quote": None}
    assert any("priority" in r["reason"] for r in rej)


def test_ac_taking_one_side_of_contradiction_dropped():
    facts = [{"id": "F1", "category": "constraint", "text": "", "quote": "web only for the first version"}]
    contra = {"id": "Q1", "category": "contradiction", "question": "Which applies?",
              "quote": "App Store and Google Play", "quote_b": "web only for the first version",
              "quote_b_": None, "related_fact_ids": [], "source": "llm"}
    bd, _, rej = filter_breakdown(_one_task_breakdown(
        acceptance_criteria=[{"text": "The platform is web-only.", "quote": "web only for the first version"},
                             {"text": "Customers can order groceries.", "quote": "to order groceries"}]),
        VAGUE, facts, [contra])
    t = bd["epics"][0]["tasks"][0]
    assert [a["quote"] for a in t["acceptance_criteria"]] == ["to order groceries"]
    assert "Q1" in t["blocked_by_question_ids"]
    assert any("contradiction" in r["reason"] for r in rej)


def test_content_word_lint_es_plural():
    tk = [{"ticket_id": "TASK-001", "title": "", "description": "",
           "acceptance_criteria": [{"text": "The app launches on 15 March 2027.",
                                    "quote": "The app must launch on 15 March 2027"}]}]
    assert content_word_lint(tk, CLEAR) == []


def test_task_from_user_fact_only_rejected():
    facts = [{"id": "F1", "category": "user", "text": "", "quote": "two user groups: members and front-desk staff"}]
    bd, _, rej = filter_breakdown(_one_task_breakdown(title="Authenticate front-desk staff"), CLEAR, facts, [])
    assert bd["epics"][0]["tasks"] == [] if bd["epics"] else True
    assert any("user/priority" in r["reason"] for r in rej)


def test_contradiction_side_lint():
    from verify import contradiction_side_lint
    q = [{"id": "Q-001", "category": "contradiction", "quote": "App Store and Google Play",
          "quote_b": "we want web only for the first version"}]
    tk = [{"ticket_id": "TASK-001", "title": "Customer Ordering (Web Platform)", "description": "",
           "acceptance_criteria": []},
          {"ticket_id": "TASK-002", "title": "Browse products", "description": "Customers browse products",
           "acceptance_criteria": []}]
    w = contradiction_side_lint(tk, q, VAGUE_S)
    assert len(w) == 1 and "TASK-001" in w[0] and "web" in w[0]


def test_meta_only_task_with_verified_ac_kept():
    facts = [{"id": "F1", "category": "user", "text": "", "quote": "Admins should get the usual reports every week."}]
    bd, _, rej = filter_breakdown(_one_task_breakdown(
        title="Generate weekly admin reports",
        acceptance_criteria=[{"text": "Admins get the usual reports every week.",
                              "quote": "Admins should get the usual reports every week."}]), VAGUE, facts, [])
    assert len(bd["epics"][0]["tasks"]) == 1


def test_missing_question_on_stated_topic_rejected():
    facts = [{"id": "F1", "category": "priority", "text": "", "quote": "Booking and cancellation are high priority"}]
    raw = {"questions": [{"id": "Q1", "category": "missing", "question": "What are the priorities for the other features?",
                          "quote": None, "quote_b": None, "related_fact_ids": []}]}
    qs, rej = check_questions(raw, CLEAR, CLEAR_S, facts)
    assert qs == [] and "topic the brief states" in rej[0]["reason"]


def test_breakdown_user_lists_avoid_words():
    import prompts
    assert "web, store" in prompts.breakdown_user("b", [], [], avoid_words=["web", "store"])
    assert "UNRESOLVED" not in prompts.breakdown_user("b", [], [])


def test_missing_question_mentioning_web_not_rejected_as_platform():
    facts = [{"id": "F1", "category": "constraint", "text": "", "quote": "web application that works in desktop and mobile browsers"}]
    raw = {"questions": [{"id": "Q1", "category": "missing",
                          "question": "How do front-desk staff identify themselves to the web application?",
                          "quote": None, "quote_b": None, "related_fact_ids": []}]}
    qs, rej = check_questions(raw, CLEAR, CLEAR_S, facts)
    assert len(qs) == 1 and rej == []


def test_transient_errors_detected():
    from llm import _is_rate_limit
    assert _is_rate_limit(Exception("503 UNAVAILABLE. high demand"))
    assert _is_rate_limit(Exception("429 RESOURCE_EXHAUSTED"))
    assert not _is_rate_limit(Exception("400 INVALID_ARGUMENT"))


def test_bare_app_is_not_a_platform():
    facts = [{"id": "F1", "category": "feature", "text": "", "quote": "Build an app."}]
    new = missing_info_scan(facts, [])
    assert any("platform" in q["question"].lower() for q in new)
    facts_web = [{"id": "F1", "category": "constraint", "text": "", "quote": "works in desktop and mobile browsers"}]
    assert not any("platform" in q["question"].lower() for q in missing_info_scan(facts_web, []))
