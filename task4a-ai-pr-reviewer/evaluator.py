"""LLM evaluator: compares a PR diff against a ticket's acceptance criteria."""
import json
import os
import re

SYSTEM_PROMPT = (
    "You are an expert Senior Code Reviewer. Compare the provided Code Diff against the "
    "provided Jira/Azure Acceptance Criteria. Answer in JSON with two keys: fulfilled "
    "(true/false) and feedback (markdown string). If fulfilled is false, provide a precise "
    "list of missing requirements or code bugs. If true, provide a brief summary of the "
    "successful verification.\n"
    "Return ONLY the JSON object."
)

DEFAULT_MODEL = "gemini-2.5-flash"

ERR_JSON = "LLM answer is not valid JSON"
ERR_FULFILLED = "fulfilled key missing or not boolean"
ERR_FEEDBACK = "feedback key missing or not a string"


def check_diff(diff, max_chars):
    """Return an error message if the diff is unusable, else None."""
    if diff is None or not isinstance(diff, str) or not diff.strip():
        return "PR diff is empty"
    if len(diff) > max_chars:
        return f"PR diff is too large ({len(diff)} chars > limit {max_chars}); manual review required"
    return None


def build_user_message(ticket, diff):
    ac = ticket.get("acceptance_criteria") or []
    lines = [
        f"Ticket ID: {ticket.get('id', '')}",
        f"Title: {ticket.get('title', '')}",
        "",
        "Acceptance Criteria:",
    ]
    lines += [f"{i}. {c}" for i, c in enumerate(ac, 1)]
    lines += ["", "Code Diff:", "```diff", diff, "```"]
    return "\n".join(lines)


_FENCE_RE = re.compile(r"^\s*```[a-zA-Z0-9_-]*\s*\n?(.*?)\n?\s*```\s*$", re.S)


def parse_verdict(text):
    """Return (verdict, None) or (None, error)."""
    if not isinstance(text, str):
        return None, ERR_JSON
    s = text.strip()
    m = _FENCE_RE.match(s)
    if m:
        s = m.group(1).strip()
    try:
        data = json.loads(s)
    except (ValueError, TypeError):
        return None, ERR_JSON
    if not isinstance(data, dict):
        return None, ERR_JSON
    fulfilled = data.get("fulfilled")
    if not isinstance(fulfilled, bool):
        return None, ERR_FULFILLED
    feedback = data.get("feedback")
    if not isinstance(feedback, str):
        return None, ERR_FEEDBACK
    return {"fulfilled": fulfilled, "feedback": feedback}, None


def _gemini_call(system, user):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")
    from google import genai
    from google.genai import types

    model = os.environ.get("GEMINI_MODEL") or DEFAULT_MODEL
    cfg = dict(
        system_instruction=system,
        response_mime_type="application/json",
        temperature=0,
        max_output_tokens=4096,
    )
    # thinking_budget=0 is valid for gemini-2.5 models; newer models reject it (400).
    if "2.5" in model:
        cfg["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
    client = genai.Client()
    resp = client.models.generate_content(
        model=model, contents=user, config=types.GenerateContentConfig(**cfg)
    )
    return resp.text or ""


def evaluate(ticket, diff, call=None):
    """Never raises. Returns {fulfilled, feedback, error, raw}."""
    result = {"fulfilled": None, "feedback": "", "error": None, "raw": ""}
    try:
        user = build_user_message(ticket, diff)
        raw = (call or _gemini_call)(SYSTEM_PROMPT, user)
        result["raw"] = raw if isinstance(raw, str) else repr(raw)
        verdict, err = parse_verdict(raw)
        if err:
            result["error"] = err
            return result
        result["fulfilled"] = verdict["fulfilled"]
        result["feedback"] = verdict["feedback"]
    except Exception as e:  # noqa: BLE001 - must never raise
        msg = str(e) or type(e).__name__
        result["error"] = msg if msg == "GEMINI_API_KEY not set" else f"LLM call failed: {type(e).__name__}: {msg}"
    return result
