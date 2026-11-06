"""Code-side checks that keep the LLM honest (PLAN.md section 3).

Nothing here calls an LLM. Every item the LLM proposes must carry a verbatim quote of the
brief; items that fail are dropped and logged in a `rejected` list with a reason.
"""
import re

# ---------------------------------------------------------------- core (exact PLAN code)


def normalise(s):
    for a, b in {"‘": "'", "’": "'", "“": '"', "”": '"',
                 "–": "-", "—": "-"}.items():
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", s).strip().lower().rstrip(".")


def quote_ok(q, brief):
    return bool(q) and isinstance(q, str) and len(normalise(q)) >= 8 \
        and normalise(q) in normalise(brief)


def sentence_of(q, sentences):  # -> "S7" or None
    if not q:
        return None
    return next((s["sid"] for s in sentences if normalise(q) in normalise(s["text"])), None)


_BULLET_RE = re.compile(r"^\s*(?:[-*•]\s|\d+[.)]\s)")
HEADING_MAX_WORDS = 6


def _is_heading(line, next_line):
    """A short line with no end punctuation followed by a capitalised line is a heading or
    label ("Mobile app for customers"), not the first half of a wrapped sentence."""
    words = line.split()
    nxt = next_line.lstrip()
    return 0 < len(words) <= HEADING_MAX_WORDS and nxt[:1].isupper()


def unwrap(brief):
    """Re-join hard-wrapped lines: a single newline that does not follow sentence-ending
    punctuation (.!?:), is not followed by a blank line or a list bullet, and does not end a
    short heading-like line, becomes a space.
    (Defect fix D1: PLAN's split on every newline cut wrapped sentences in two, so quotes that
    ran across a line wrap had no sentence id and contradictions were wrongly rejected.
    Review fix: a short heading line is no longer merged into the next sentence.)"""
    lines = brief.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    buf = [lines[0]]
    prev_line = lines[0]
    for nxt in lines[1:]:
        s = prev_line.rstrip()
        join = (s and nxt.strip() and s[-1] not in ".!?:"
                and not _BULLET_RE.match(nxt) and not _is_heading(s, nxt))
        if join:
            buf[-1] = buf[-1].rstrip() + " " + nxt.lstrip()
        else:
            buf.append(nxt)
        prev_line = nxt
    return "\n".join(buf)


def split_sentences(brief):
    pieces = re.split(r"(?<=[.!?])\s+|\n+", unwrap(brief))
    out = []
    for p in pieces:
        p = p.strip()
        if p:
            out.append({"sid": f"S{len(out) + 1}", "text": p})
    return out


# ---------------------------------------------------------------- helpers

FACT_CATEGORIES = {"goal", "feature", "user", "constraint", "integration",
                   "deadline", "priority", "estimate"}
QUESTION_CATEGORIES = {"missing", "vague", "contradiction", "undefined_term", "scope_gap"}


def _num(id_, prefix):
    m = re.fullmatch(prefix + r"-?0*(\d+)", str(id_ or "").strip())
    return int(m.group(1)) if m else 0


def _next_q(questions):
    return max([_num(q.get("id"), "Q") for q in questions] + [0]) + 1


def _items(raw, key):
    if not isinstance(raw, dict):
        return []
    v = raw.get(key)
    return v if isinstance(v, list) else []


def _rej(stage, item, reason):
    return {"stage": stage, "item": item, "reason": reason}


def _has_digit(s):
    return bool(s) and bool(re.search(r"\d", s))


def _quote_fail_reason(q, brief):
    """Why quote_ok failed: a real but too-short quote gets its own reason (review fix:
    'Admins' was logged as 'quote not in brief' although the word is in the brief)."""
    if isinstance(q, str) and normalise(q) and normalise(q) in normalise(brief) \
            and len(normalise(q)) < 8:
        return "quote too short (<8 chars)"
    return "quote not in brief"


def _str_list(v):
    """LLM lists may hold non-strings ([["Q1"]], {...}); keep only string ids.
    (Review fix: an unhashable element crashed set/`in` checks with a raw traceback.)"""
    if not isinstance(v, list):
        return []
    return [x.strip() for x in v if isinstance(x, str) and x.strip()]


def _overlap(a, b):
    """True if one normalised quote contains the other."""
    if not (isinstance(a, str) and isinstance(b, str)):
        return False
    na, nb = normalise(a), normalise(b)
    return bool(na) and bool(nb) and (na in nb or nb in na)


# ---------------------------------------------------------------- Stage 2


def filter_facts(raw, brief):
    """Keep facts whose quote is a verbatim substring of the brief.

    Returns (facts, rejected). Duplicate or missing ids are renumbered to the next free F<n>.
    """
    facts, rejected, seen = [], [], set()
    candidates = _items(raw, "facts")
    next_id = max([_num(f.get("id"), "F") for f in candidates if isinstance(f, dict)] + [0]) + 1
    for f in candidates:
        if not isinstance(f, dict):
            rejected.append(_rej("understand", f, "not a JSON object"))
            continue
        if not quote_ok(f.get("quote"), brief):
            rejected.append(_rej("understand", f, _quote_fail_reason(f.get("quote"), brief)))
            continue
        cat = str(f.get("category") or "").strip().lower()
        if cat not in FACT_CATEGORIES:
            rejected.append(_rej("understand", f, f"unknown category '{cat}'"))
            continue
        fid = str(f.get("id") or "").strip()
        if not fid or fid in seen:
            fid = f"F{next_id}"
            next_id += 1
        seen.add(fid)
        facts.append({"id": fid, "category": cat,
                      "text": str(f.get("text") or f.get("quote")).strip(),
                      "quote": f["quote"].strip()})
    return facts, rejected


# ---------------------------------------------------------------- Stage 3


_EXAMPLE_RES = [
    re.compile(r"\s*\((?:e\.\s?g\.?|eg|i\.\s?e\.?|for example|for instance|such as|like)[^)]*\)", re.I),
    re.compile(r",?\s+(?:such as|for example|for instance|e\.\s?g\.?)\s+[^?]*(?=\?)", re.I),
]


def strip_examples(text):
    """Remove example answers the LLM suggested inside a question ("(e.g., CSV, PDF)",
    ", such as X or Y?"). The golden rule says a question never proposes an answer."""
    out = text
    for rx in _EXAMPLE_RES:
        out = rx.sub("", out)
    out = re.sub(r"\s+([?.,])", r"\1", out).strip()
    return out


def check_questions(raw, brief, sentences, facts):
    """Verify LLM questions. Returns (questions, rejected)."""
    fact_ids = {f["id"] for f in facts}
    questions, rejected, seen = [], [], set()
    candidates = _items(raw, "questions")
    next_id = max([_num(q.get("id"), "Q") for q in candidates if isinstance(q, dict)] + [0]) + 1
    for q in candidates:
        if not isinstance(q, dict):
            rejected.append(_rej("gaps", q, "not a JSON object"))
            continue
        cat = str(q.get("category") or "").strip().lower()
        text = str(q.get("question") or "").strip()
        quote, quote_b = q.get("quote"), q.get("quote_b")
        if cat not in QUESTION_CATEGORIES:
            rejected.append(_rej("gaps", q, f"unknown category '{cat}'"))
            continue
        if not text:
            rejected.append(_rej("gaps", q, "empty question"))
            continue
        if cat == "contradiction":
            if not (quote_ok(quote, brief) and quote_ok(quote_b, brief)):
                rejected.append(_rej("gaps", q, "contradiction needs two verified quotes"))
                continue
            na, nb = normalise(quote), normalise(quote_b)
            sa, sb = sentence_of(quote, sentences), sentence_of(quote_b, sentences)
            if sa is None or sb is None or sa == sb or na in nb or nb in na:
                rejected.append(_rej("gaps", q, "contradiction quotes same sentence/nested"))
                continue
        else:
            if quote not in (None, "") and not quote_ok(quote, brief):
                rejected.append(_rej("gaps", q, _quote_fail_reason(quote, brief)))
                continue
            if quote in (None, "") and cat != "missing":
                rejected.append(_rej("gaps", q, f"'{cat}' question needs a quote"))
                continue
            quote = quote or None
            quote_b = None  # quote_b is only meaningful for contradictions
        if cat == "missing":
            covered = next((narrow for (_, needed, _), narrow in
                            zip(_TEMPLATES, _COVERED_TOPIC_RES)
                            if not needed(facts) and re.search(narrow, text, re.I)), None)
            if covered:
                rejected.append(_rej("gaps", q, "'missing' question about a topic the brief states"))
                continue
        cleaned = strip_examples(text)
        if cleaned != text:
            rejected.append(_rej("gaps", {"id": q.get("id"), "question": text},
                                 "suggested example answers removed from question"))
            text = cleaned
        qid = str(q.get("id") or "").strip()
        if not qid or qid in seen:
            qid = f"Q{next_id}"
            next_id += 1
        seen.add(qid)
        rel = [r for r in _str_list(q.get("related_fact_ids")) if r in fact_ids]
        questions.append({"id": qid, "category": cat, "question": text,
                          "quote": quote.strip() if quote else None,
                          "quote_b": quote_b.strip() if quote_b else None,
                          "related_fact_ids": rel, "source": "llm"})
    return questions, rejected


# Defect fix: PLAN's pattern "web|mobile|app|ios|..." treated the bare word "app" (and any
# substring such as "happen", "application") as a stated platform, so "Build an app." got no
# platform question. Only real platform words / stores count now.
PLATFORM_RE = re.compile(r"\b(web|mobile|ios|android|desktop|browsers?|app store|google play)\b",
                         re.I)

# (topic regex over existing question text, condition-fn, templated question)
_TEMPLATES = [
    (r"target users|user roles?|user groups?|who (are|will be) the users|who will use",
     lambda facts: not any(f["category"] == "user" for f in facts),
     "Who are the target users / user roles?"),
    (r"deadline|launch date|go[- ]live|live date|release date|as soon as possible|\basap\b",
     lambda facts: not any(f["category"] == "deadline" and _has_digit(f["quote"]) for f in facts),
     "What is the deadline or launch date?"),
    (r"platform|\bweb\b|mobile|\bios\b|android|desktop|browser|app store|google play",
     lambda facts: not any(PLATFORM_RE.search(f["quote"]) for f in facts),
     "Which platform(s) must be supported?"),
    (r"integrat",
     lambda facts: not any(f["category"] == "integration" for f in facts),
     "Does the system need to integrate with any existing systems (payments, accounts, "
     "notifications)? If so, which?"),
    (r"priorit",
     lambda facts: not any(f["category"] == "priority" for f in facts),
     "Which features have the highest priority for the first release?"),
]


# Narrow topic patterns for rejecting an LLM "missing" question whose topic the brief states.
# (Defect: reusing the broad platform pattern \bweb\b rejected "How do front-desk staff
# identify themselves to the web application?", a real gap.) Same order as _TEMPLATES.
_COVERED_TOPIC_RES = [
    r"target users|user roles|user groups|who (are|will be) the (target )?users",
    r"deadline|launch date|go[- ]live date|release date",
    r"\bplatforms?\b",
    r"integrat",
    r"priorit",
]


FIELD_TOPIC_RES = {
    "priority": r"priorit|\brank",
    # "launch" alone: a real run asked "What is the specific target date for the live launch?"
    # and the deadline template was still added as a duplicate.
    "deadline": r"deadline|\blaunch|go[- ]live|live date|release date|target date"
                r"|as soon as possible|\basap\b",
    "estimate": r"\bestimat|\beffort\b|how long will",
}
_TEMPLATE_FIELD = {1: "deadline", 4: "priority"}   # index into _TEMPLATES


def field_question(field, questions, facts):
    """Id of the question that asks for a ticket field (priority / deadline / estimate) for
    the whole project, or None. A question counts only if it is about the field AND is a
    whole-brief question (no quote), or relates to a fact of that field's category, or
    relates to no feature fact. (Review fix: "What does 'important' mean for delivery slots
    in terms of their priority...?" is about one feature and must not stand in for a
    project-wide priority ranking.)"""
    cat = {f["id"]: f.get("category") for f in facts}
    for q in questions:
        if not re.search(FIELD_TOPIC_RES[field], str(q.get("question") or ""), re.I):
            continue
        rel = [cat.get(r) for r in q.get("related_fact_ids") or []]
        if q.get("quote") is None or field in rel or "feature" not in rel:
            return q["id"]
    return None


def missing_info_scan(facts, questions):
    """Templated questions for missing basics (no LLM). Returns only the NEW questions."""
    new, n = [], _next_q(questions)
    asked = " | ".join(q.get("question", "") for q in questions).lower()
    for i, (topic_re, needed, text) in enumerate(_TEMPLATES):
        field = _TEMPLATE_FIELD.get(i)
        if field:
            covered = field_question(field, questions, facts) is not None
        else:
            covered = bool(re.search(topic_re, asked, re.I))
        if needed(facts) and not covered:
            new.append({"id": f"Q{n}", "category": "missing", "question": text,
                        "quote": None, "quote_b": None, "related_fact_ids": [],
                        "source": "template"})
            n += 1
    return new


# ---------------------------------------------------------------- Stage 4


def clean_ac_text(text):
    t = re.sub(r"[\r\n]+", " ", str(text or ""))
    t = t.strip()
    while True:
        t2 = re.sub(r"^(h3\.|\*)\s*", "", t)
        if t2 == t:
            break
        t = t2
    return re.sub(r"\s+", " ", t).strip()


def _field(val):
    if isinstance(val, dict):
        return val.get("value"), val.get("quote")
    return val, None


def _blank(v):
    return v is None or (isinstance(v, str) and v.strip().lower() in ("", "not specified", "null", "none"))


def _list(v):
    return v if isinstance(v, list) else []


META_CATEGORIES = {"user", "priority", "deadline", "estimate"}
PRIORITY_RE = re.compile(r"\b(priority|priorities|highest|high|medium|low|lowest)\b", re.I)
PRIORITY_LEVELS = ("highest", "lowest", "high", "medium", "low")
FIELDS = ("priority", "estimate", "deadline")


def priority_level(value):
    """The priority level word in a value ('high priority' -> 'high'), or None."""
    v = str(value or "").lower()
    return next((lvl for lvl in PRIORITY_LEVELS if re.search(r"\b" + lvl + r"\b", v)), None)


def _value_problem(name, value, q, brief):
    """Reason to drop a stated priority/estimate/deadline value, or None if it is supported.
    (Review fix: only the quote used to be checked, so an invented value such as 'Highest'
    could ride on any genuine quote. Now the value itself must be in its quote.)"""
    if not quote_ok(q, brief):
        return f"{name} quote not in brief"
    if name == "deadline" and not _has_digit(q):
        return "deadline quote has no digit (not a concrete date)"
    if name == "priority" and not PRIORITY_RE.search(q):
        return "priority quote states no priority level"
    nv, nq = normalise(str(value)), normalise(q)
    if name == "priority" and priority_level(value):
        if not re.search(r"\b" + priority_level(value) + r"\b", nq):
            return "value not supported by quote"
    elif not nv or nv not in nq:
        return "value not supported by quote"
    return None


_SUBJECT_STOP = {"with", "that", "this", "they", "them", "their", "have", "will", "must",
                 "should", "only", "after", "before", "from", "into", "each", "also", "when",
                 "then", "able", "user", "users", "priority", "priorities", "highest", "high",
                 "medium", "lowest", "low"}


def _subject_stems(text):
    """4-letter stems of the content words in text ('cancellation' -> 'canc')."""
    return {w[:4] for w in re.findall(r"[a-z]+", str(text or "").lower())
            if len(w) >= 4 and w not in _SUBJECT_STOP}


def priority_names_task(pq, title, task_quotes):
    """True if priority quote pq names this task's subject. (Defect D31: "Booking and
    cancellation are high priority." gave 'Identify as a member' Priority High, because
    only the level word was checked. A priority now needs a shared content word between
    its quote and the task's title / own quotes.)"""
    own = _subject_stems(title)
    for tq in task_quotes:
        if normalise(tq) != normalise(pq):
            own |= _subject_stems(tq)
    return bool(_subject_stems(pq) & own)


def _overlaps(q, cq):
    """True if quote q is (part of) either side of contradiction question cq."""
    return any(_overlap(q, side) for side in (cq.get("quote"), cq.get("quote_b")) if side)


def _dedupe(ids):
    out = []
    for x in ids:
        if x not in out:
            out.append(x)
    return out


def filter_breakdown(raw, brief, facts, questions):
    """Drop everything in the LLM breakdown that the brief does not support.

    Returns (breakdown, new_questions, rejected). new_questions are dependency / AC / field
    questions raised by code (source "breakdown"); ids continue the Q numbering.
    """
    fact_ids = {f["id"] for f in facts}
    fact_quote = {f["id"]: f.get("quote") for f in facts}
    fact_cat = {f["id"]: f.get("category") for f in facts}
    q_by_id = {q["id"]: q for q in questions}
    contra = [q for q in questions if q.get("category") == "contradiction"]
    field_q = {name: field_question(name, questions, facts) for name in FIELDS}
    rejected, new_q = [], []
    next_q = [_next_q(questions)]

    def add_q(text, category="missing"):
        qid = f"Q{next_q[0]}"
        next_q[0] += 1
        new_q.append({"id": qid, "category": category, "question": text, "quote": None,
                      "quote_b": None, "related_fact_ids": [], "source": "breakdown"})
        return qid

    epics, used_ids = [], set()

    def uniq(lid, fallback):
        lid = (lid.strip() if isinstance(lid, str) else "") or fallback
        base, k = lid, 2
        while lid in used_ids:
            lid = f"{base}_{k}"
            k += 1
        used_ids.add(lid)
        return lid

    # pass 1: epics, tasks, AC, scalar fields, question links
    for ei, e in enumerate(_items(raw, "epics"), 1):
        if not isinstance(e, dict):
            rejected.append(_rej("breakdown", e, "epic is not a JSON object"))
            continue
        epic = {"local_id": uniq(e.get("local_id"), f"E{ei}"),
                "title": str(e.get("title") or "").strip(),
                "description": str(e.get("description") or "").strip(),
                "quote": e.get("quote").strip() if quote_ok(e.get("quote"), brief) else None,
                "tasks": []}
        if e.get("quote") and epic["quote"] is None:
            rejected.append(_rej("breakdown", {"epic": epic["title"], "quote": e.get("quote")},
                                 "epic quote not in brief (dropped)"))
        lost = 0
        for ti, t in enumerate(_list(e.get("tasks")), 1):
            if not isinstance(t, dict):
                rejected.append(_rej("breakdown", t, "task is not a JSON object"))
                lost += 1
                continue
            title = str(t.get("title") or "").strip()
            src = [s for s in _str_list(t.get("source_fact_ids")) if s in fact_ids]
            if not src:
                rejected.append(_rej("breakdown", t, "task has no verified source facts (invented)"))
                lost += 1
                continue
            if not title:
                rejected.append(_rej("breakdown", t, "task has no title"))
                lost += 1
                continue
            ttype = str(t.get("type") or "Task").strip().capitalize()
            task = {"local_id": uniq(t.get("local_id"), f"{epic['local_id']}.T{ti}"),
                    "type": ttype if ttype in ("Story", "Task") else "Task",
                    "title": title,
                    "description": str(t.get("description") or "").strip(),
                    "source_fact_ids": src, "acceptance_criteria": [],
                    "dependencies": [], "_raw_deps": _list(t.get("dependencies")),
                    "blocked_by_question_ids": []}
            code_links = []
            for fid in src:
                for cq in contra:
                    if _overlaps(fact_quote.get(fid), cq):
                        code_links.append(cq["id"])
            for ac in _list(t.get("acceptance_criteria")):
                text = clean_ac_text(ac.get("text") if isinstance(ac, dict) else ac)
                q = ac.get("quote") if isinstance(ac, dict) else None
                side = next((cq for cq in contra if _overlaps(q, cq)), None)
                if side is not None:
                    rejected.append(_rej("breakdown", {"task": title, "ac": ac},
                                         f"acceptance criterion takes one side of contradiction {side['id']}"))
                    code_links.append(side["id"])
                    continue
                if not text:
                    rejected.append(_rej("breakdown", {"task": title, "ac": ac}, "empty acceptance criterion"))
                elif not quote_ok(q, brief):
                    rejected.append(_rej("breakdown", {"task": title, "ac": ac},
                                         "acceptance criterion quote not in brief"))
                else:
                    task["acceptance_criteria"].append({"text": text, "quote": q.strip()})
            if not task["acceptance_criteria"] and all(fact_cat.get(x) in META_CATEGORIES for x in src):
                # defect fix: "Authenticate front-desk staff" was built from the user-group fact
                # alone, with no verified criterion: a user/priority/deadline fact says who or
                # when, not what to build. (Category is LLM-assigned, so a meta-only task that
                # still has a verified criterion is kept.)
                rejected.append(_rej("breakdown", t, "task sourced only from user/priority/"
                                     "deadline/estimate facts and no verified acceptance criterion"))
                lost += 1
                continue
            if not task["acceptance_criteria"]:
                code_links.append(add_q(f"What testable acceptance conditions apply to '{title}'?"))
            null_field_qids = []
            for name in FIELDS:
                value, q = _field(t.get(name))
                if _blank(value):
                    task[name] = {"value": None, "quote": None}
                    if field_q[name]:
                        null_field_qids.append(field_q[name])
                    continue
                reason = _value_problem(name, value, q, brief)
                if reason is None and name == "priority" and not priority_names_task(
                        q, title, [a["quote"] for a in task["acceptance_criteria"]]
                        + [fact_quote[s] for s in src]):
                    reason = "priority quote names other features, not this task"
                if reason is None:
                    lvl = priority_level(value) if name == "priority" else None
                    task[name] = {"value": lvl.capitalize() if lvl else str(value).strip(),
                                  "quote": q.strip()}
                    continue
                rejected.append(_rej("breakdown", {"task": title, name: t.get(name)}, reason))
                task[name] = {"value": None, "quote": None}
                # PLAN: a dropped value is "Not specified" AND a question is raised.
                null_field_qids.append(field_q[name] or add_q(f"What is the {name} for '{title}'?"))
            code_links += null_field_qids
            # LLM links are kept only when the question is about THIS task: a contradiction,
            # a question whose quote is (part of) one of the task's source/AC quotes, or the
            # question for one of its "Not specified" fields. (Review fix: whole-brief or
            # other-sentence questions blocked unrelated tasks, so almost nothing was Ready.)
            task_quotes = ([a["quote"] for a in task["acceptance_criteria"]]
                           + [fact_quote[s] for s in src])
            kept, dropped = [], []
            for qid in _str_list(t.get("blocked_by_question_ids")):
                q = q_by_id.get(qid)
                if q is None:
                    continue  # unknown id, dropped below
                if (q.get("category") == "contradiction" or qid in null_field_qids
                        or any(_overlap(q.get("quote"), tq) for tq in task_quotes)):
                    kept.append(qid)
                else:
                    dropped.append(qid)
            if dropped:
                rejected.append(_rej("breakdown", {"task": title, "blocked_by_dropped": dropped},
                                     "question link dropped: question is not about this task "
                                     "(its quote is not one of the task's source/AC quotes)"))
            task["blocked_by_question_ids"] = _dedupe(kept + code_links)
            epic["tasks"].append(task)
        if not epic["tasks"] and epic["quote"] is None:
            rejected.append(_rej("breakdown", {"epic": epic["title"]},
                                 "epic has no verified quote and no valid tasks"))
            continue
        if lost and epic["tasks"]:
            # Review fix: an epic description written for a task that was then rejected
            # (e.g. "identification for members and staff" after the staff task was dropped)
            # kept describing the rejected scope. Rebuild it from the surviving tasks.
            rejected.append(_rej("breakdown", {"epic": epic["title"], "description": epic["description"]},
                                 "epic description replaced: it was written with task(s) that were rejected"))
            epic["description"] = "Covers: " + "; ".join(x["title"] for x in epic["tasks"]) + "."
        if not epic["title"]:
            epic["title"] = epic["tasks"][0]["title"] if epic["tasks"] else epic["quote"]
        epics.append(epic)

    # pass 2: dependencies (need the full set of surviving task ids)
    task_titles = {t["local_id"]: t["title"] for e in epics for t in e["tasks"]}
    epic_ids = {e["local_id"] for e in epics}
    for e in epics:
        for t in e["tasks"]:
            for d in t.pop("_raw_deps"):
                target = d.get("local_id") if isinstance(d, dict) else d
                q = d.get("quote") if isinstance(d, dict) else None
                target = target.strip() if isinstance(target, str) else None
                if target in epic_ids:
                    rejected.append(_rej("breakdown", {"task": t["title"], "dependency": d},
                                         "dependency target is an epic (only task-to-task links)"))
                    continue
                if target not in task_titles or target == t["local_id"]:
                    rejected.append(_rej("breakdown", {"task": t["title"], "dependency": d},
                                         "dependency target unknown"))
                    continue
                if not quote_ok(q, brief):
                    rejected.append(_rej("breakdown", {"task": t["title"], "dependency": d},
                                         "dependency quote not in brief (turned into a question)"))
                    t["blocked_by_question_ids"].append(
                        add_q(f"Does {t['title']} depend on {task_titles[target]}?"))
                    continue
                if target not in [x["local_id"] for x in t["dependencies"]]:
                    t["dependencies"].append({"local_id": target, "quote": q.strip()})

    # blocked_by links must point to known questions
    known = {q["id"] for q in questions} | {q["id"] for q in new_q}
    for e in epics:
        for t in e["tasks"]:
            t["blocked_by_question_ids"] = _dedupe(
                [qid for qid in t["blocked_by_question_ids"] if qid in known])
    return {"epics": epics}, new_q, rejected


# ---------------------------------------------------------------- lints (final tickets)

DENYLIST = ["stripe", "paypal", "react", "angular", "vue", "aws", "azure", "firebase", "oauth",
            "jwt", "sql", "postgres", "mongodb", "ios", "android", "kubernetes", "docker", "sms",
            "email", "push", "refund", "invoice", "currency", "waitlist", "waiting list",
            "notification", "login", "password", "dashboard"]
NUMBER_RE = re.compile(r"\d+\s?(?:ms\b|seconds?\b|%)", re.I)

STOPWORDS = set("""
a about above after again against all also am an and any are aren't as at be because been
before being below between both but by can cannot could couldn't did didn't do does doesn't
doing don't down during each either else ever every few for from further had hadn't has hasn't
have haven't having he her here hers herself him himself his how however i if in into is isn't
it it's its itself just least less let like made make makes many may me might more most much
must my myself neither never no nor not now of off often on once only onto or other others
otherwise our ours ourselves out over own per rather same shall she should shouldn't since so
some such than that that's the their theirs them themselves then there these they this those
though through thus to too under until up upon us very via was wasn't we were weren't what
when where whether which while who whom whose why will with within without would wouldn't yet
you your yours yourself yourselves
able already always another anyone anything become becomes correct correctly each ensure
ensures exist exists given gets into least lets make must need needs only ones same sure
""".split())
# Review fix: domain words (system, user, value, item, verify, show, new) were in STOPWORDS,
# which hid unsourced uses of them; they are linted like any other content word now.

# Generic ticket-writing words allowed in titles/descriptions (not in AC, which must reuse the
# brief's words). They describe the work, not the product, so they cannot invent a feature.
GENERIC_TICKET_WORDS = set("""
ability able add adding allow allows build building capability cover covers create creating define defined
deliver develop developing development display enable enables existing feature features flow
function functionality implement implementing mechanism option provide provides providing
requirement requirements set setup stated story support supports task tasks use used uses using
work works
""".split())


def _ticket_texts(t):
    yield "title", t.get("title") or ""
    yield "description", t.get("description") or ""
    for ac in t.get("acceptance_criteria") or []:
        yield "AC", (ac.get("text") if isinstance(ac, dict) else str(ac)) or ""


def invention_lint(tickets, brief):
    nb = normalise(brief)
    warnings = []
    for t in tickets:
        tid = t.get("ticket_id", "?")
        hits = []
        blob = " ".join(text for _, text in _ticket_texts(t)).lower()
        for term in DENYLIST:
            # Review fix: any inflection counts (refunded, refunding, invoiced, logins), not
            # only -s/-es. A final "e" is dropped for long terms so "invoicing" also matches.
            stem = term[:-1] if len(term) >= 6 and term.endswith("e") else term
            if re.search(r"\b" + re.escape(stem) + r"\w*", blob) \
                    and not re.search(r"\b" + re.escape(stem), nb):
                hits.append(term)
        for m in NUMBER_RE.finditer(blob):
            if normalise(m.group(0)) not in nb and m.group(0) not in hits:
                hits.append(m.group(0))
        for h in hits:
            warnings.append(f"WARNING invented term: {h} in {tid}")
    return warnings


def _stem(w):
    return w[:-1] if w.endswith("s") else w


def _stems(text):
    words = re.findall(r"[a-z]+", text.lower())
    return {_stem(w) for w in words} | {w[:-2] for w in words if w.endswith("es")}


def _variants(w):
    """w plus simple -ing / -ed base forms (receiving -> receive, booked -> book)."""
    out = {w}
    for suf in ("ing", "ed"):
        if w.endswith(suf) and len(w) > len(suf) + 2:
            base = w[:-len(suf)]
            out |= {base, base + "e"}
            if len(base) > 2 and base[-1] == base[-2]:
                out.add(base[:-1])            # stopped -> stop
    return out


def _unsourced(text, allowed, extra=frozenset()):
    out = []
    for w in re.findall(r"[a-z]+", (text or "").lower()):
        if len(w) < 4 or w in STOPWORDS or w in extra:
            continue
        stem = _stem(w)
        if (stem in allowed or (w.endswith("es") and w[:-2] in allowed)
                or stem in STOPWORDS or stem in extra
                or any(v in allowed or v in extra for v in _variants(w))):
            continue
        if w not in out:
            out.append(w)
    return out


def content_word_lint(tickets, brief):
    """Unsourced content words. AC text: PLAN rule (brief + that criterion's own quote).
    Review fix: titles and descriptions are checked too (an epic was titled "Order Management
    System Integration" for the undefined acronym ORMS), with a small allowlist of generic
    ticket-writing verbs such as implement / provide / enable."""
    brief_stems = _stems(normalise(brief))
    warnings = []
    for t in tickets:
        tid = t.get("ticket_id", "?")
        for where in ("title", "description"):
            for w in _unsourced(t.get(where) or "", brief_stems, GENERIC_TICKET_WORDS):
                warnings.append(f"WARNING unsourced word '{w}' in {where} of {tid}")
        seen = set()
        for ac in t.get("acceptance_criteria") or []:
            text = ac.get("text") if isinstance(ac, dict) else str(ac)
            quote = ac.get("quote") if isinstance(ac, dict) else ""
            for w in _unsourced(text, brief_stems | _stems(quote or "")):
                if w not in seen:
                    seen.add(w)
                    warnings.append(f"WARNING unsourced word '{w}' in AC of {tid}")
    return warnings


def sanitize_descriptions(tickets, brief):
    """Replace a description that contains a denylist term the brief never uses with neutral
    text built by code, so an invented term (e.g. 'notifications') never reaches the export.
    Returns rejected-log entries. (Review fix: the lint only warned; the CSV kept the text.)"""
    rejected = []
    by_id = {t.get("ticket_id"): t for t in tickets}
    for t in tickets:
        probe = {"ticket_id": t.get("ticket_id"), "description": t.get("description") or ""}
        hits = invention_lint([probe], brief)
        if not hits:
            continue
        if t.get("type") == "Epic":
            kids = [by_id[c]["title"] for c in t.get("children") or [] if c in by_id]
            neutral = ("Covers: " + "; ".join(kids) + ".") if kids else "Not specified"
        else:
            ref = t.get("source_reference")
            neutral = f"As stated in the brief: {ref}" if ref not in (None, "", "Not specified") \
                else "Not specified"
        rejected.append(_rej("lint", {"ticket": t.get("ticket_id"),
                                      "description": t.get("description"), "warnings": hits},
                             "description used a term not in the brief; replaced with neutral text"))
        t["description"] = neutral
    return rejected


def contradiction_side_lint(tickets, questions, sentences):
    """Warn when a ticket's title/description/AC uses a word that appears ONLY in the sentence
    of one side of a contradiction - i.e. the ticket may have picked that side.
    (Defect: an epic was titled "... (Web Platform)" while web vs app stores was unresolved.)"""
    def words(text):
        return {w for w in re.findall(r"[a-z]+", normalise(text or "")) if len(w) >= 3
                and w not in STOPWORDS}
    warnings = []
    for q in questions:
        if q.get("category") != "contradiction":
            continue
        for side_key in ("quote", "quote_b"):
            sid = sentence_of(q.get(side_key), sentences)
            if not sid:
                continue
            others = set()
            for s in sentences:
                if s["sid"] != sid:
                    others |= words(s["text"])
            distinctive = words(q.get(side_key)) - others
            for t in tickets:
                blob = words(" ".join(text for _, text in _ticket_texts(t)))
                hit = sorted(distinctive & blob)
                if hit:
                    warnings.append(f"WARNING {t.get('ticket_id', '?')} may pick one side of "
                                    f"contradiction {q.get('id')}: {', '.join(hit)}")
    return warnings


def contradiction_side_words(questions, sentences):
    """Words that occur only in the sentence of one side of a contradiction (sorted)."""
    out = set()
    for q in questions:
        if q.get("category") != "contradiction":
            continue
        for side_key in ("quote", "quote_b"):
            sid = sentence_of(q.get(side_key), sentences)
            if not sid:
                continue
            others = set()
            for s in sentences:
                if s["sid"] != sid:
                    others |= _lint_words(s["text"])
            out |= _lint_words(q.get(side_key)) - others
    return sorted(out)


def _lint_words(text):
    return {w for w in re.findall(r"[a-z]+", normalise(text or "")) if len(w) >= 3
            and w not in STOPWORDS}
