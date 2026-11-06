"""Stage 5: turn the verified breakdown into Jira-style ticket records (plain code, no LLM).

PLAN.md section 3, Stage 5:
- IDs TASK-001.. in order: epic, its tasks, next epic, ...
- dependencies remapped through the local_id -> ticket id map (unknown ids dropped)
- open questions = blocked_by_question_ids UNION questions whose related_fact_ids overlap
  the task's source_fact_ids; questions renumbered Q-001..
- unlinked questions are attached to every epic AND listed as general questions
- null priority / estimate / deadline -> "Not specified"
- epics: acceptance_criteria [] and children = child ticket ids
- status: task Ready if no open questions, else Needs clarification;
  epic Needs clarification if it or any child is.
"""
from verify import normalise as _norm, quote_ok, sentence_of


NOT_SPECIFIED = "Not specified"
READY = "Ready"
NEEDS = "Needs clarification"
TASK_TYPES = ("Story", "Task")


def _sid_span(quote, sentences):
    """'S7' for a quote inside one sentence; 'S5-S6' for a verified quote that crosses a
    sentence boundary (review fix: such a reference used to lose its 'Sn:' prefix)."""
    sid = sentence_of(quote, sentences)
    if sid:
        return sid
    nq = _norm(quote)
    for size in range(2, len(sentences) + 1):          # smallest span first
        for i in range(len(sentences) - size + 1):
            j = i + size - 1
            joined = " ".join(s.get("text", "") for s in sentences[i:j + 1])
            if nq in _norm(joined):
                return f"{sentences[i]['sid']}-{sentences[j]['sid']}"
    return None


def _ref(quote, sentences, brief_text):
    """('S4: "quote"', single_sentence) for a verified quote, else (None, False)."""
    if not isinstance(quote, str) or not quote_ok(quote, brief_text):
        return None, False
    sid = _sid_span(quote, sentences)
    if not sid:
        return f'"{quote}"', False
    return f'{sid}: "{quote}"', "-" not in sid


def _overlap(a, b):
    if not (isinstance(a, str) and isinstance(b, str)):
        return False
    na, nb = _norm(a), _norm(b)
    return bool(na) and bool(nb) and (na in nb or nb in na)


def _field(obj):
    """priority/estimate/deadline -> string value or 'Not specified'."""
    value = obj.get("value") if isinstance(obj, dict) else obj
    if value is None or (isinstance(value, str) and not value.strip()):
        return NOT_SPECIFIED
    return str(value).strip()


def _q_obj(q):
    return {"id": q["new_id"], "category": q.get("category"), "question": q.get("question"),
            "quote": q.get("quote"), "quote_b": q.get("quote_b")}


def build_tickets(breakdown, facts, questions, sentences):
    brief_text = "\n".join(s.get("text", "") for s in sentences)
    epics = (breakdown or {}).get("epics") or []
    fact_by_id = {f["id"]: f for f in facts}

    # Renumber questions Q-001.. (keep original order); map old id -> record.
    qrecs = []
    q_by_old = {}
    for i, q in enumerate(questions, 1):
        rec = dict(q)
        rec["new_id"] = f"Q-{i:03d}"
        rec["linked_tickets"] = []
        qrecs.append(rec)
        if q.get("id") is not None and q["id"] not in q_by_old:
            q_by_old[q["id"]] = rec

    # Pass 1: assign ticket ids epic-then-tasks and build local_id map.
    counter = 0
    local_map = {}
    plan = []  # (epic_id, epic, [(task_id, task)])
    for epic in epics:
        counter += 1
        eid = f"TASK-{counter:03d}"
        if epic.get("local_id"):
            local_map.setdefault(epic["local_id"], eid)
        kids = []
        for task in epic.get("tasks") or []:
            counter += 1
            tid = f"TASK-{counter:03d}"
            if task.get("local_id"):
                local_map.setdefault(task["local_id"], tid)
            kids.append((tid, task))
        plan.append((eid, epic, kids))

    # Pass 2: build task tickets and collect question links.
    linked = set()
    tickets = []
    for eid, epic, kids in plan:
        child_tickets = []
        for tid, task in kids:
            src_ids = [fid for fid in (task.get("source_fact_ids") or []) if fid in fact_by_id]
            src_set = set(src_ids)
            # source reference from first verified source fact quote
            # Prefer facts that describe the work itself; user / priority / deadline facts
            # only name who or when (defect: every member task cited "two user groups").
            # A quote inside one sentence beats one that spans sentences.
            source_reference, cross = None, None
            ranked = sorted(src_ids, key=lambda fid: fact_by_id[fid].get("category")
                            in ("user", "priority", "deadline", "estimate"))
            for fid in ranked:
                ref, single = _ref(fact_by_id[fid].get("quote"), sentences, brief_text)
                if ref and single:
                    source_reference = ref
                    break
                cross = cross or ref
            source_reference = source_reference or cross
            # dependencies remapped, unknown/self dropped, deduped
            deps = []
            for d in task.get("dependencies") or []:
                lid = d.get("local_id") if isinstance(d, dict) else d
                mapped = local_map.get(lid)
                if mapped and mapped != tid and mapped not in deps:
                    deps.append(mapped)
            # open questions: blocked_by UNION related-fact questions, in question order.
            # Review fix: a related-fact question is added only if its quote is (part of) one
            # of this task's AC quotes (or its source quotes when it has no AC). One fact can
            # cover several tasks ("browse, add to basket and pay"), so a fact overlap alone
            # put the basket and payment questions on the browse task.
            blocked = {b for b in (task.get("blocked_by_question_ids") or []) if isinstance(b, str)}
            ac_quotes = [c.get("quote") for c in task.get("acceptance_criteria") or []
                         if isinstance(c, dict) and c.get("quote")]
            own_quotes = ac_quotes or [fact_by_id[f].get("quote") for f in src_ids]
            oq = []
            for rec in qrecs:
                if rec.get("id") in blocked and q_by_old.get(rec.get("id")) is rec:
                    hit = True
                else:
                    hit = (bool(src_set & set(rec.get("related_fact_ids") or []))
                           and any(_overlap(rec.get("quote"), tq) for tq in own_quotes))
                if hit:
                    oq.append(rec)
                    linked.add(rec["new_id"])
                    rec["linked_tickets"].append(tid)
            ac = []
            for c in task.get("acceptance_criteria") or []:
                if isinstance(c, dict) and c.get("text"):
                    ac.append({"text": c["text"], "quote": c.get("quote")})
            ttype = task.get("type") if task.get("type") in TASK_TYPES else "Task"
            child_tickets.append({
                "ticket_id": tid,
                "title": task.get("title") or "",
                "type": ttype,
                "parent": eid,
                "children": [],
                "description": task.get("description") or "",
                "acceptance_criteria": ac,
                "source_reference": source_reference or NOT_SPECIFIED,
                "dependencies": deps,
                "open_questions": [_q_obj(r) for r in oq],
                "priority": _field(task.get("priority")),
                "estimate": _field(task.get("estimate")),
                "deadline": _field(task.get("deadline")),
                "status": NEEDS if oq else READY,
            })
        epic_ref, _ = _ref(epic.get("quote"), sentences, brief_text)
        if not epic_ref:
            epic_ref = next((c["source_reference"] for c in child_tickets
                             if c["source_reference"] != NOT_SPECIFIED), NOT_SPECIFIED)
        # Review fix: an epic shows a deadline when every child states the same one.
        kid_deadlines = {c["deadline"] for c in child_tickets}
        epic_deadline = (kid_deadlines.pop() if len(kid_deadlines) == 1 else NOT_SPECIFIED) \
            if child_tickets else NOT_SPECIFIED
        epic_ticket = {
            "ticket_id": eid,
            "title": epic.get("title") or "",
            "type": "Epic",
            "parent": None,
            "children": [c["ticket_id"] for c in child_tickets],
            "description": epic.get("description") or "",
            "acceptance_criteria": [],
            "source_reference": epic_ref,
            "dependencies": [],
            "open_questions": [],
            "priority": NOT_SPECIFIED,
            "estimate": NOT_SPECIFIED,
            "deadline": epic_deadline,
            "status": READY,
        }
        tickets.append(epic_ticket)
        tickets.extend(child_tickets)

    # Unlinked questions -> every epic + general questions.
    unlinked = [r for r in qrecs if r["new_id"] not in linked]
    by_id = {t["ticket_id"]: t for t in tickets}
    for t in tickets:
        if t["type"] != "Epic":
            continue
        t["open_questions"] = [_q_obj(r) for r in unlinked]
        for r in unlinked:
            r["linked_tickets"].append(t["ticket_id"])
        child_needs = any(by_id[c]["status"] == NEEDS for c in t["children"])
        t["status"] = NEEDS if (t["open_questions"] or child_needs) else READY

    def _public(r):
        out = {"id": r["new_id"], "category": r.get("category"), "question": r.get("question"),
               "quote": r.get("quote"), "quote_b": r.get("quote_b"),
               "related_fact_ids": list(r.get("related_fact_ids") or []),
               "source": r.get("source"), "linked_tickets": list(r["linked_tickets"])}
        return out

    all_q = [_public(r) for r in qrecs]
    general = [_public(r) for r in unlinked]
    return {"tickets": tickets, "questions": all_q, "general_questions": general}
