"""Orchestrates one PR review: PR -> ticket -> AC -> diff -> LLM verdict -> action.

Safety rule: MERGE only when the LLM verdict has fulfilled is True (a real bool)
and no error. Every other outcome BLOCKS.
"""
import code_fetcher
import config
import evaluator
import executor
import story_fetcher


def _log(stage, msg):
    print(f"[{stage}/6 {_NAMES[stage]}] {msg}", flush=True)


_NAMES = {1: "webhook", 2: "story", 3: "code", 4: "llm", 5: "decision", 6: "action"}


def _max_diff():
    try:
        return int(config.get("MAX_DIFF_CHARS", getattr(config, "MAX_DIFF_CHARS", 60000)))
    except (TypeError, ValueError):
        return 60000


def _finish(repo, pr, ticket_id, verdict, dry_run):
    passed = executor.is_pass(verdict) if hasattr(executor, "is_pass") else (
        verdict.get("fulfilled") is True and not verdict.get("error"))
    decision = "MERGE" if passed else "BLOCK"
    reason = verdict.get("reason") or ""
    _log(5, f"decision={decision} reason={reason}")
    try:
        actions = executor.act(repo, pr, verdict, dry_run)
    except Exception as e:  # GitHub action failed; report it
        actions = [f"ERROR performing actions: {e}"]
        if decision == "MERGE":
            decision = "BLOCK"
            reason = f"{reason}; merge action failed: {e}"
    for a in actions:
        _log(6, a)
    return {"ticket_id": ticket_id, "decision": decision, "reason": reason,
            "actions": actions, "verdict": verdict}


def _block(repo, pr, ticket_id, reason, dry_run, feedback="", raw=None):
    verdict = {"fulfilled": False, "feedback": feedback, "error": reason, "reason": reason}
    if raw is not None:
        verdict["raw"] = raw
    return _finish(repo, pr, ticket_id, verdict, dry_run)


def review_pr(repo, number, dry_run=False, call=None):
    _log(1, f"reviewing {repo}#{number}{' (dry-run)' if dry_run else ''}")
    try:
        pr = code_fetcher.fetch_pr(repo, number)
    except Exception as e:
        reason = f"Could not fetch PR: {e}"
        _log(1, f"ERROR {reason} - no action taken")
        return {"ticket_id": None, "decision": "BLOCK", "reason": reason,
                "actions": [], "verdict": None}
    _log(1, f"PR #{pr.get('number')} '{pr.get('title')}' branch={pr.get('head_ref')} sha={str(pr.get('head_sha'))[:7]}")

    ticket_id = story_fetcher.extract_ticket_id(pr.get("head_ref") or "", pr.get("title") or "")
    if not ticket_id:
        _log(2, "no ticket ID in branch or title")
        return _block(repo, pr, None,
                      "No ticket ID (e.g. PROJ-123) found in the branch name or PR title.", dry_run)
    _log(2, f"ticket ID {ticket_id}")
    try:
        ticket = story_fetcher.fetch_ticket(ticket_id)
    except Exception as e:
        _log(2, f"ERROR fetching ticket: {e}")
        return _block(repo, pr, ticket_id, f"Could not fetch ticket {ticket_id}: {e}", dry_run)
    ac = ticket.get("acceptance_criteria") or []
    _log(2, f"'{ticket.get('title')}' source={ticket.get('source')} AC={len(ac)}")
    if not ac:
        return _block(repo, pr, ticket_id,
                      f"Ticket {ticket_id} has no acceptance criteria; cannot verify the PR.", dry_run)

    try:
        diff = code_fetcher.fetch_diff(repo, number)
    except Exception as e:
        _log(3, f"ERROR fetching diff: {e}")
        return _block(repo, pr, ticket_id, f"Could not fetch PR diff: {e}", dry_run)
    _log(3, f"diff {len(diff or '')} chars")
    diff_err = evaluator.check_diff(diff, _max_diff())
    if diff_err:
        _log(3, f"ERROR {diff_err}")
        return _block(repo, pr, ticket_id, diff_err, dry_run)

    _log(4, "asking LLM for a verdict")
    try:
        result = evaluator.evaluate(ticket, diff, call=call)
    except Exception as e:  # evaluate should never raise, but be safe
        result = {"fulfilled": None, "feedback": "", "error": f"LLM error: {e}", "raw": ""}
    fulfilled = result.get("fulfilled")
    err = result.get("error")
    _log(4, f"fulfilled={fulfilled!r} error={err}")
    if err:
        return _block(repo, pr, ticket_id, f"LLM evaluation failed: {err}", dry_run,
                      feedback=result.get("feedback") or "", raw=result.get("raw"))
    if fulfilled is not True:
        reason = ("Acceptance criteria not fulfilled." if fulfilled is False
                  else "LLM verdict did not contain a boolean 'fulfilled'.")
        verdict = {"fulfilled": False if fulfilled is False else None,
                   "feedback": result.get("feedback") or "", "error": None if fulfilled is False else reason,
                   "reason": reason, "raw": result.get("raw")}
        return _finish(repo, pr, ticket_id, verdict, dry_run)

    verdict = {"fulfilled": True, "feedback": result.get("feedback") or "", "error": None,
               "reason": "All acceptance criteria fulfilled.", "raw": result.get("raw")}
    return _finish(repo, pr, ticket_id, verdict, dry_run)
