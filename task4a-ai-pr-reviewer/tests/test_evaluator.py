import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import evaluator  # noqa: E402

TICKET = {
    "id": "TASK-004",
    "title": "Add login rate limiting",
    "description": "",
    "acceptance_criteria": [
        "Block after 5 failed attempts",
        "Return HTTP 429 when blocked",
        "Reset counter after 15 minutes",
    ],
    "source": "csv",
}
DIFF = "diff --git a/app.py b/app.py\n+def login():\n+    pass\n"


def fixed(text):
    seen = {}

    def call(system, user):
        seen["system"], seen["user"] = system, user
        return text

    call.seen = seen
    return call


def test_system_prompt_contains_blueprint():
    assert "You are an expert Senior Code Reviewer." in evaluator.SYSTEM_PROMPT
    assert "fulfilled (true/false) and feedback (markdown string)" in evaluator.SYSTEM_PROMPT
    assert "Return ONLY the JSON object." in evaluator.SYSTEM_PROMPT


def test_valid_true():
    r = evaluator.evaluate(TICKET, DIFF, call=fixed('{"fulfilled": true, "feedback": "All good"}'))
    assert r["fulfilled"] is True and r["error"] is None and r["feedback"] == "All good"


def test_valid_false():
    r = evaluator.evaluate(TICKET, DIFF, call=fixed('{"fulfilled": false, "feedback": "- missing 429"}'))
    assert r["fulfilled"] is False and r["error"] is None
    assert "429" in r["feedback"]


def test_prose_answer_is_error():
    r = evaluator.evaluate(TICKET, DIFF, call=fixed("Looks great, ship it!"))
    assert r["fulfilled"] is None
    assert r["error"] == "LLM answer is not valid JSON"
    assert r["raw"] == "Looks great, ship it!"


def test_fenced_json_ok():
    r = evaluator.evaluate(TICKET, DIFF, call=fixed('```json\n{"fulfilled": true, "feedback": "ok"}\n```'))
    assert r["fulfilled"] is True and r["error"] is None


def test_fulfilled_missing():
    r = evaluator.evaluate(TICKET, DIFF, call=fixed('{"feedback": "ok"}'))
    assert r["fulfilled"] is None and r["error"] == "fulfilled key missing or not boolean"


def test_fulfilled_string_true():
    r = evaluator.evaluate(TICKET, DIFF, call=fixed('{"fulfilled": "true", "feedback": "ok"}'))
    assert r["fulfilled"] is None and r["error"] == "fulfilled key missing or not boolean"


def test_fulfilled_int_one_rejected():
    v, err = evaluator.parse_verdict('{"fulfilled": 1, "feedback": "ok"}')
    assert v is None and err


def test_feedback_missing():
    r = evaluator.evaluate(TICKET, DIFF, call=fixed('{"fulfilled": true}'))
    assert r["fulfilled"] is None and r["error"]


def test_non_dict_json():
    v, err = evaluator.parse_verdict("[true]")
    assert v is None and err == "LLM answer is not valid JSON"


def test_call_raising_is_error():
    def boom(system, user):
        raise ConnectionError("network down")

    r = evaluator.evaluate(TICKET, DIFF, call=boom)
    assert r["fulfilled"] is None and "network down" in r["error"]


def test_missing_key_default_call(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    r = evaluator.evaluate(TICKET, DIFF)
    assert r["fulfilled"] is None and r["error"] == "GEMINI_API_KEY not set"


def test_empty_and_whitespace_diff():
    assert evaluator.check_diff("", 1000)
    assert evaluator.check_diff("  \n\t ", 1000)
    assert evaluator.check_diff(None, 1000)


def test_oversized_diff():
    assert evaluator.check_diff("x" * 101, 100)
    assert evaluator.check_diff("x" * 100, 100) is None


def test_user_message_contains_every_ac():
    call = fixed('{"fulfilled": true, "feedback": "ok"}')
    evaluator.evaluate(TICKET, DIFF, call=call)
    user = call.seen["user"]
    assert "TASK-004" in user and "Add login rate limiting" in user
    for i, ac in enumerate(TICKET["acceptance_criteria"], 1):
        assert f"{i}. {ac}" in user
    assert "```diff\n" + DIFF in user
    assert call.seen["system"] == evaluator.SYSTEM_PROMPT
