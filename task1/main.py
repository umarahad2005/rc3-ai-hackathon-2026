"""Brief2Jira CLI - turn a raw client brief into a breakdown, Jira tickets and open questions.

Usage: python main.py <brief> [--out DIR] [--model M]

Stages (PLAN.md section 2):
  1 Input (code) -> 2 Understand (LLM) -> 3 Gaps (LLM) -> 4 Break down (LLM)
  -> 5 Tickets (code) -> 6 Output (code)
Exit codes: 1 empty/unreadable brief or usage error (before any API or key check),
            2 GEMINI_API_KEY not set, 3 a stage failed; no partial export is written then.
"""
import argparse
import datetime as _dt
import json
import os
import sys

import envfile  # noqa: F401  loads .env (if present) before anything reads os.environ
import export
import llm
import prompts
import tickets as tickets_mod
import verify


class Tee:
    """Collects everything printed so run.log is an exact copy of the console."""

    def __init__(self):
        self.lines = []

    def __call__(self, text=""):
        text = str(text)
        print(text)
        self.lines.append(text)

    def save(self, path):
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(self.lines) + "\n")


def _utf8_console():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def load_brief(path):
    """Stage 1: read as UTF-8, strip BOM, refuse empty. Returns (brief, sentences)."""
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            brief = f.read()
    except OSError as e:
        print(f"ERROR: cannot read brief: {e}", file=sys.stderr)
        sys.exit(1)
    except UnicodeDecodeError:
        print("ERROR: brief is not valid UTF-8", file=sys.stderr)
        sys.exit(1)
    brief = brief.lstrip("﻿")
    if not brief.strip():
        print("ERROR: brief is empty", file=sys.stderr)
        sys.exit(1)
    return brief, verify.split_sentences(brief)


def _header(out, title):
    out("")
    out("#" * 78)
    out(f"# {title}")
    out("#" * 78)


def _print_rejected(out, rejected):
    if not rejected:
        out("Rejected: None")
        return
    out(f"Rejected ({len(rejected)}):")
    for r in rejected:
        out(f"  [{r.get('stage')}] {r.get('reason')}: {json.dumps(r.get('item'), ensure_ascii=False)}")


def _print_questions(out, questions, grouped=False):
    if grouped:
        # Review fix: Stage 3 output is grouped by category (PLAN P4).
        order = {c: i for i, c in enumerate(export.QUESTION_CATEGORIES)}
        questions = sorted(questions, key=lambda q: order.get(q.get("category"), len(order)))
    last = None
    for q in questions:
        if grouped and q.get("category") != last:
            last = q.get("category")
            out(f"  [{last}]")
        out(f"  {q['id']} ({q['category']}, {q.get('source')}) {q['question']}")
        if q.get("quote"):
            out(f'      quote: "{q["quote"]}"')
        if q.get("quote_b"):
            out(f'      quote_b: "{q["quote_b"]}"')
        if q.get("related_fact_ids"):
            out(f"      related facts: {', '.join(q['related_fact_ids'])}")


def run(brief_path, out_dir, model):
    out = Tee()
    brief, sentences = load_brief(brief_path)          # exit 1 before any API/key check
    if not os.environ.get("GEMINI_API_KEY"):
        print("ERROR: GEMINI_API_KEY not set", file=sys.stderr)
        sys.exit(2)
    os.makedirs(out_dir, exist_ok=True)
    # Defect fix (D30): deleting old exports at the start meant a failed run (503 overload)
    # wiped the last good tickets.json / tickets_jira.csv. Now a failed run never touches
    # run.log or the exports; it writes failed_run.log instead, so run.log always matches
    # the exports beside it (the D13 concern) and a good result is never lost.
    rejected = []
    try:
        out(f"Brief2Jira  brief={brief_path}  model={model}  out={out_dir}")

        # ---- Stage 1
        _header(out, f"STAGE 1 INPUT - {len(sentences)} sentences")
        for s in sentences:
            out(f"  {s['sid']}: {s['text']}")

        # ---- Stage 2
        _header(out, "STAGE 2 UNDERSTAND (LLM) - verified facts")
        raw = llm.call_json(prompts.UNDERSTAND, prompts.understand_user(brief), model=model,
                            max_tokens=8192, stage="understand", out_dir=out_dir, log=out)
        facts, rej = verify.filter_facts(raw, brief)
        rejected += rej
        for f in facts:
            out(f"  {f['id']} [{f['category']}] {f['text']}")
            out(f'      quote: "{f["quote"]}"  ({verify.sentence_of(f["quote"], sentences) or "?"})')
        _print_rejected(out, rej)

        # ---- Stage 3
        _header(out, "STAGE 3 GAPS (LLM + templates) - verified questions")
        raw = llm.call_json(prompts.GAPS, prompts.gaps_user(brief, facts), model=model,
                            max_tokens=8192, stage="gaps", out_dir=out_dir, log=out)
        questions, rej = verify.check_questions(raw, brief, sentences, facts)
        rejected += rej
        templ = verify.missing_info_scan(facts, questions)
        questions += templ
        _print_questions(out, questions, grouped=True)
        out(f"Templated questions added: {len(templ)}")
        _print_rejected(out, rej)

        # ---- Stage 4
        _header(out, "STAGE 4 BREAK DOWN (LLM) - verified epics and tasks")
        llm_questions = [{k: q[k] for k in ("id", "category", "question", "quote",
                                            "quote_b", "related_fact_ids")} for q in questions]
        raw = llm.call_json(prompts.BREAKDOWN, prompts.breakdown_user(
                                brief, facts, llm_questions,
                                avoid_words=verify.contradiction_side_words(questions, sentences)),
                            model=model, max_tokens=16384, stage="breakdown", out_dir=out_dir, log=out)
        breakdown, new_q, rej = verify.filter_breakdown(raw, brief, facts, questions)
        rejected += rej
        questions += new_q
        for e in breakdown["epics"]:
            out(f"  {e['local_id']} {e['title']}")
            for t in e["tasks"]:
                deps = ", ".join(d["local_id"] for d in t["dependencies"]) or "-"
                out(f"    {t['local_id']} [{t['type']}] {t['title']}  facts={','.join(t['source_fact_ids'])}"
                    f"  AC={len(t['acceptance_criteria'])}  deps={deps}"
                    f"  blocked_by={','.join(t['blocked_by_question_ids']) or '-'}")
        if new_q:
            out("Questions raised by code in Stage 4:")
            _print_questions(out, new_q)
        _print_rejected(out, rej)

        # ---- Stage 5
        result = tickets_mod.build_tickets(breakdown, facts, questions, sentences)
        rejected += verify.sanitize_descriptions(result["tickets"], brief)
        lint = (verify.invention_lint(result["tickets"], brief)
                + verify.content_word_lint(result["tickets"], brief)
                + verify.contradiction_side_lint(result["tickets"], result["questions"], sentences))

        # ---- Stage 6
        _header(out, "STAGE 5+6 TICKETS AND REPORT")
        for line in export.format_console(result, facts, rejected, lint).rstrip("\n").split("\n"):
            out(line)
        meta = {"brief_file": brief_path.replace("\\", "/"), "model": model,
                "generated_at": _dt.datetime.now().astimezone().isoformat(timespec="seconds")}
        # Build both files in temp names first, then swap in, so an export error cannot
        # leave a half-written or mismatched pair.
        tmp_json = os.path.join(out_dir, "tickets.json.tmp")
        tmp_csv = os.path.join(out_dir, "tickets_jira.csv.tmp")
        export.to_json(tmp_json, meta, result, rejected, lint)
        export.to_csv(tmp_csv, result["tickets"])
        os.replace(tmp_json, os.path.join(out_dir, "tickets.json"))
        os.replace(tmp_csv, os.path.join(out_dir, "tickets_jira.csv"))
        out("")
        out(f"Wrote {os.path.join(out_dir, 'tickets.json')}, "
            f"{os.path.join(out_dir, 'tickets_jira.csv')}, {os.path.join(out_dir, 'run.log')}")
    except Exception as e:  # noqa: BLE001 - every stage failure -> exit 3, never a traceback
        # Review fix: only StageError was caught, so e.g. a malformed LLM list crashed with a
        # raw traceback, exit 1 and no run.log. Any failure now ends the run cleanly.
        if isinstance(e, llm.StageError):
            out(f"ERROR: stage failed: {e}")
        else:
            out(f"ERROR: stage failed: unexpected {type(e).__name__}: {e}")
        for partial in ("tickets.json.tmp", "tickets_jira.csv.tmp"):
            try:
                os.remove(os.path.join(out_dir, partial))
            except OSError:
                pass
        out("No export written. Any earlier successful run.log / tickets.json / "
            "tickets_jira.csv in this folder were left unchanged.")
        try:
            out.save(os.path.join(out_dir, "failed_run.log"))
        except OSError:
            pass
        sys.exit(3)
    out.save(os.path.join(out_dir, "run.log"))
    try:
        os.remove(os.path.join(out_dir, "failed_run.log"))   # it described an older failure
    except FileNotFoundError:
        pass
    return 0


class _ArgParser(argparse.ArgumentParser):
    """Usage errors exit 1 (bad input), so exit 2 always means 'GEMINI_API_KEY not set'."""

    def error(self, message):
        self.print_usage(sys.stderr)
        print(f"{self.prog}: error: {message}", file=sys.stderr)
        sys.exit(1)


def main(argv=None):
    _utf8_console()
    p = _ArgParser(description="Brief2Jira: brief -> breakdown, Jira tickets, open questions")
    p.add_argument("brief", help="path to the brief text file")
    p.add_argument("--out", help="output directory (default out/<brief stem>)")
    p.add_argument("--model", default=None, help="Gemini model (default GEMINI_MODEL or gemini-flash-lite-latest)")
    a = p.parse_args(argv)
    stem = os.path.splitext(os.path.basename(a.brief))[0]
    out_dir = a.out or os.path.join("out", stem)
    return run(a.brief, out_dir, a.model or llm.DEFAULT_MODEL)


if __name__ == "__main__":
    sys.exit(main())
