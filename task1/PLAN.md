# PLAN - Brief2Jira (Task 1)
Drafted with AI help in chats/00_planning_chat.md; reviewed in P1 of chats/01_build_chat.md. Full spec: PLAN_full.md.

**Goal:** brief file -> structured breakdown + Jira-style tickets + open questions, never assuming.
Anything the brief does not state becomes "Not specified" AND an open question.

**Stages:** 1 Input (code) | 2 Understand (LLM) | 3 Gaps (LLM + code templates) | 4 Break down (LLM) | 5 Tickets (code) | 6 Output (code)

**LLM vs code:** the LLM (Google Gemini via `google-genai`, JSON mode, temperature 0, 3 calls per run)
only *proposes* facts, questions and epics/tasks as strict JSON. Code verifies every quote
against the brief, rejects and logs failures, checks contradictions (two quotes, different
sentences, not nested), adds missing-info questions from templates, drops unquoted acceptance
criteria / dependencies / priority / estimate / deadline values, lints for invented terms,
assigns TASK-001.., sets "Not specified" and status, and exports JSON + Jira CSV.

**Ticket fields (same on every ticket):** ID, title, type (Epic/Story/Task), parent/children,
description, acceptance criteria (each with its quote), source reference (`S7: "quote"`),
dependencies, open questions, priority / estimate / deadline (or Not specified), status
(Ready / Needs clarification; an epic inherits from its children).

**Jira CSV:** Summary, Issue Type, Description (`h3. Acceptance Criteria` + `* ` bullets, then
Source, Dependencies, Open Questions, Details), Priority (blank unless stated), Labels = TASK-00x.
Track A reads the criteria back with `export.parse_ac()`; `[]` means do not merge.

**Files:** main.py (CLI), llm.py, prompts.py, verify.py, tickets.py, export.py, tests/.

**Tests:** see TESTING.md (quote checks, contradiction rules, 8 traps, status, CSV round-trip,
edge cases: empty / whitespace / "Build an app." / missing key).

**Demo briefs:** briefs/clear.txt (gym class booking), briefs/vague.txt (grocery app with 8 traps).

**Exit codes:** 1 empty brief or usage error (before any API call), 2 GEMINI_API_KEY not set, 3 a stage failed (no partial export).

**Changes after P1 review:** pending - to be filled after the P1 review in chats/01_build_chat.md
