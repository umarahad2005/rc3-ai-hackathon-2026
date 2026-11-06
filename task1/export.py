"""Stage 6: output (plain code). Console report, tickets.json and tickets_jira.csv.

PLAN.md section 3 Stage 6 and section 4. The Description column uses Jira wiki markup with an
exact "h3. Acceptance Criteria" + "* " bullet contract that parse_ac() (shared with Track A) reads.
"""
import csv
import json
import re
from collections import Counter

CSV_COLUMNS = ["Summary", "Issue Type", "Description", "Priority", "Labels"]
QUESTION_CATEGORIES = ["missing", "vague", "contradiction", "undefined_term", "scope_gap"]


def parse_ac(desc):
    m = re.search(r"h3\.\s*Acceptance Criteria\s*\n(.*?)(?=\nh3\.|\Z)", desc, re.S)
    return [l[2:].strip() for l in m.group(1).splitlines() if l.startswith("* ")] if m else []


def _one_line(s):
    """Collapse newlines so a value cannot break the wiki-markup sections."""
    return re.sub(r"\s*\n\s*", " ", str(s or "")).strip()


def _children_text(ticket):
    return ", ".join(ticket.get("children") or []) or "(none)"


def description_for(ticket):
    is_epic = ticket.get("type") == "Epic"
    lines = [_one_line(ticket.get("description")) or "Not specified", "",
             "h3. Acceptance Criteria"]
    if is_epic:
        lines.append(f"Not applicable (epic) - see child tickets {_children_text(ticket)}")
    else:
        ac = [_one_line(c.get("text")) for c in ticket.get("acceptance_criteria") or []]
        ac = [a for a in ac if a]
        lines += [f"* {a}" for a in ac] if ac else ["None stated in brief"]
    lines += ["", "h3. Source", f"{{quote}}{_one_line(ticket.get('source_reference'))}{{quote}}",
              "", "h3. Dependencies",
              ", ".join(ticket.get("dependencies") or []) or "None stated in brief",
              "", "h3. Open Questions"]
    oq = ticket.get("open_questions") or []
    lines += [f"* [{q['id']}] {_one_line(q.get('question'))}" for q in oq] if oq else ["None"]
    lines += ["", "h3. Details",
              f"Status: {ticket.get('status')} | Parent: {ticket.get('parent') or 'None'} | "
              f"Priority: {ticket.get('priority')} | Estimate: {ticket.get('estimate')} | "
              f"Deadline: {ticket.get('deadline')}"]
    return "\n".join(lines)


def jira_priority(value):
    """Map a stated priority word to a Jira priority; anything else -> '' (blank)."""
    if not value or not isinstance(value, str):
        return ""
    v = value.strip().lower()
    if v == "not specified":
        return ""
    if re.search(r"\bhighest\b", v):
        return "Highest"
    if re.search(r"\bhigh\b", v):
        return "High"
    if re.search(r"\bmedium\b", v):
        return "Medium"
    if re.search(r"\b(low|lowest)\b", v):
        return "Low"
    return ""


def to_csv(path, tickets):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, quoting=csv.QUOTE_ALL)
        w.writerow(CSV_COLUMNS)
        for t in tickets:
            w.writerow([t.get("title") or "", t.get("type") or "", description_for(t),
                        jira_priority(t.get("priority")), t.get("ticket_id") or ""])


def to_json(path, meta, result, rejected, lint_warnings):
    data = dict(meta or {})
    data["tickets"] = result.get("tickets", [])
    data["general_questions"] = result.get("general_questions", [])
    data["questions"] = result.get("questions", [])
    data["rejected"] = list(rejected or [])
    data["lint_warnings"] = list(lint_warnings or [])
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _fmt_item(item):
    if isinstance(item, (dict, list)):
        return json.dumps(item, ensure_ascii=False)
    return str(item)


def format_console(result, facts, rejected, lint_warnings):
    tickets = result.get("tickets", [])
    questions = result.get("questions", [])
    general = result.get("general_questions", [])
    rejected = list(rejected or [])
    lint_warnings = list(lint_warnings or [])
    out = []
    bar = "=" * 78

    out += [bar, f"TICKETS ({len(tickets)})", bar]
    for t in tickets:
        out.append(f"{t['ticket_id']}  [{t['type']}]  {t['title']}")
        if t["type"] == "Epic":
            out.append(f"  Children: {_children_text(t)}")
        else:
            out.append(f"  Parent: {t.get('parent') or 'None'}")
        out.append(f"  Description: {t.get('description') or ''}")
        if t["type"] == "Epic":
            out.append(f"  Acceptance Criteria: Not applicable (epic) - see child tickets "
                       f"{_children_text(t)}")
        else:
            ac = t.get("acceptance_criteria") or []
            if ac:
                out.append("  Acceptance Criteria:")
                for c in ac:
                    out.append(f'    - {c.get("text")}   <- "{c.get("quote")}"')
            else:
                out.append("  Acceptance Criteria: None stated in brief")
        out.append(f"  Source: {t.get('source_reference')}")
        out.append(f"  Dependencies: {', '.join(t.get('dependencies') or []) or 'None stated in brief'}")
        out.append(f"  Priority: {t.get('priority')}")
        out.append(f"  Estimate: {t.get('estimate')}")
        out.append(f"  Deadline: {t.get('deadline')}")
        out.append(f"  Status: {t.get('status')}")
        oq = t.get("open_questions") or []
        if oq:
            out.append("  Open Questions:")
            for q in oq:
                out.append(f"    [{q['id']}] ({q.get('category')}) {q.get('question')}")
        else:
            out.append("  Open Questions: None")
        out.append("")

    out += [bar, f"OPEN QUESTIONS BY CATEGORY ({len(questions)})", bar]
    cats = QUESTION_CATEGORIES + sorted({q.get("category") or "uncategorised" for q in questions}
                                        - set(QUESTION_CATEGORIES))
    for cat in cats:
        qs = [q for q in questions if (q.get("category") or "uncategorised") == cat]
        if not qs:
            continue
        out.append(f"[{cat}] ({len(qs)})")
        for q in qs:
            out.append(f"  {q['id']}: {q.get('question')}")
            if cat == "contradiction":
                out.append(f'      quote A: "{q.get("quote")}"')
                out.append(f'      quote B: "{q.get("quote_b")}"')
            elif q.get("quote"):
                out.append(f'      quote: "{q.get("quote")}"')
            linked = ", ".join(q.get("linked_tickets") or []) or "none"
            out.append(f"      linked tickets: {linked}")
        out.append("")
    out.append(f"General questions (not linked to a specific task, attached to every epic): "
               f"{', '.join(q['id'] for q in general) or 'None'}")
    out.append("")

    out += [bar, f"REJECTED ITEMS ({len(rejected)})", bar]
    if rejected:
        for r in rejected:
            if isinstance(r, dict):
                out.append(f"  [{r.get('stage')}] {r.get('reason')}: {_fmt_item(r.get('item'))}")
            else:
                out.append(f"  {_fmt_item(r)}")
    else:
        out.append("  None")
    out.append("")

    out += [bar, f"LINT WARNINGS ({len(lint_warnings)})", bar]
    out += [f"  {w}" for w in lint_warnings] if lint_warnings else ["  None"]
    out.append("")

    out += [bar, "COUNTS", bar]
    out.append(f"  Facts: {len(facts or [])}")
    qc = Counter(q.get("category") or "uncategorised" for q in questions)
    out.append(f"  Questions: {len(questions)}"
               + (" (" + ", ".join(f"{c}: {qc[c]}" for c in cats if qc.get(c)) + ")" if qc else ""))
    sc = Counter(t.get("status") for t in tickets)
    out.append(f"  Tickets: {len(tickets)} (Ready: {sc.get('Ready', 0)}, "
               f"Needs clarification: {sc.get('Needs clarification', 0)})")
    out.append(f"  Rejected items: {len(rejected)}")
    out.append(f"  Lint warnings: {len(lint_warnings)}")
    return "\n".join(out) + "\n"
