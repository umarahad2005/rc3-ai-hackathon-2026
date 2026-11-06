"""Gemini wrapper: one function, call_json(), that returns a parsed JSON object.

Rules (PLAN.md section 2, llm.py rules):
- key only from env var GEMINI_API_KEY (missing -> message on stderr, exit 2)
- model from GEMINI_MODEL env var or parameter, default gemini-flash-lite-latest (gemini-2.5-flash is not available to new keys)
- JSON mode, temperature 0, explicit max_output_tokens
- MAX_TOKENS finish reason or empty text -> StageError("output truncated"), no retry
- HTTP 429 / RESOURCE_EXHAUSTED -> wait 30 s, retry once, then StageError
- invalid JSON -> retry once with the parse error; 2nd failure -> save raw reply to
  out_dir/failed_<stage>.txt and raise StageError
"""
import json
import os
import re
import sys
import time

DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-lite-latest")
RATE_LIMIT_WAIT_S = 30


class StageError(Exception):
    """A pipeline stage failed in a way the run cannot recover from (exit code 3)."""


def _require_key():
    if not os.environ.get("GEMINI_API_KEY"):
        print("ERROR: GEMINI_API_KEY not set", file=sys.stderr)
        sys.exit(2)


def strip_fences(text):
    """Remove ``` / ```json fences around a reply, if present."""
    t = (text or "").strip()
    m = re.match(r"^```[a-zA-Z]*\s*\n?(.*?)\n?```\s*$", t, re.S)
    return m.group(1).strip() if m else t


def _parse(text):
    """json.loads the fence-stripped text; the top level must be an object."""
    obj = json.loads(strip_fences(text))
    if not isinstance(obj, dict):
        raise ValueError("top-level JSON value is not an object")
    return obj


def _is_rate_limit(err):
    """True for transient errors worth one wait-and-retry: 429 RESOURCE_EXHAUSTED and
    (defect fix, seen in a real run) 503 UNAVAILABLE "model is experiencing high demand"."""
    code = getattr(err, "code", None) or getattr(err, "status_code", None)
    msg = str(err)
    return (code in (429, 503) or "RESOURCE_EXHAUSTED" in msg or "UNAVAILABLE" in msg
            or " 429" in msg or " 503" in msg)


def _is_daily_quota(err):
    """True when the 429 is the free tier's DAILY request quota: waiting 30 s cannot help,
    so fail at once (review fix: the run used to sleep 30 s for nothing)."""
    msg = str(err)
    return "PerDay" in msg or "per day" in msg.lower()


def _stderr_log(text):
    print(text, file=sys.stderr)


def _generate(client, model, contents, system, max_tokens, log=None):
    """One generate_content call, with the single 429 retry. Returns the reply text."""
    from google.genai import types

    cfg = dict(
        system_instruction=system,
        response_mime_type="application/json",
        temperature=0,
        max_output_tokens=max_tokens,
    )
    budget = os.environ.get("GEMINI_THINKING_BUDGET")
    if budget not in (None, ""):
        cfg["thinking_config"] = types.ThinkingConfig(thinking_budget=int(budget))
    config = types.GenerateContentConfig(**cfg)

    for attempt in (1, 2):
        try:
            resp = client.models.generate_content(model=model, contents=contents, config=config)
            break
        except Exception as e:  # SDK raises google.genai.errors.APIError subclasses
            if _is_rate_limit(e) and _is_daily_quota(e):
                detail = re.sub(r"\s+", " ", str(e))[:400]
                raise StageError("Gemini free-tier DAILY quota exhausted; re-run after the quota "
                                 f"resets. API said: {detail}") from e
            if _is_rate_limit(e) and attempt == 1:
                (log or _stderr_log)(f"Transient API error (429/503). Waiting {RATE_LIMIT_WAIT_S} s "
                                     "and retrying once...")
                time.sleep(RATE_LIMIT_WAIT_S)
                continue
            if _is_rate_limit(e):
                detail = re.sub(r"\s+", " ", str(e))[:400]
                raise StageError("Gemini rate limit / overload (429 or 503) "
                                 f"hit twice; wait a minute and re-run. API said: {detail}") from e
            raise StageError(f"Gemini API error: {type(e).__name__}: {e}") from e

    finish = ""
    try:
        finish = str(resp.candidates[0].finish_reason or "")
    except (AttributeError, IndexError, TypeError):
        pass
    text = None
    try:
        text = resp.text
    except Exception:
        text = None
    if "MAX_TOKENS" in finish or not (text or "").strip():
        raise StageError(f"output truncated (finish_reason={finish or 'unknown'}, "
                         f"max_output_tokens={max_tokens})")
    return text


def call_json(system, user, model=None, max_tokens=8192, stage="stage", out_dir=None, log=None):
    """Send system+user to Gemini in JSON mode and return the parsed dict.

    log: optional callable(str) for progress notices (main passes its Tee so the retry notice
    is also in run.log); default prints to stderr."""
    _require_key()
    from google import genai
    from google.genai import types

    model = model or DEFAULT_MODEL
    client = genai.Client()  # reads GEMINI_API_KEY from the environment

    first = _generate(client, model, user, system, max_tokens, log)
    try:
        return _parse(first)
    except ValueError as err:  # json.JSONDecodeError is a ValueError
        first_err = err

    retry_msg = (f"Your previous reply was not valid JSON: {first_err}. "
                 "Return ONLY the JSON.")
    contents = [
        types.Content(role="user", parts=[types.Part(text=user)]),
        types.Content(role="model", parts=[types.Part(text=first)]),
        types.Content(role="user", parts=[types.Part(text=retry_msg)]),
    ]
    second = _generate(client, model, contents, system, max_tokens, log)
    try:
        return _parse(second)
    except ValueError as err:
        path = None
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
            path = os.path.join(out_dir, f"failed_{stage}.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write("=== first reply ===\n" + first + "\n\n=== retry reply ===\n" + second)
        where = f"; raw reply saved to {path}" if path else ""
        raise StageError(f"{stage}: reply was not valid JSON after one retry ({err}){where}") from err
