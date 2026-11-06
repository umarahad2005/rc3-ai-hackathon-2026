# TASK 1 Implementation Plan: Brief2Jira

*Provenance: this plan was drafted with AI help in a planning conversation that merged three drafts, D1 (no-assumption-first), D2 (time-boxed MVP) and D3 (evaluation and integration), and a reviewer fixed 14 gaps. The LLM was then switched to Google Gemini (free tier) because no Anthropic API key was available. That conversation is exported unedited as `chats/00_planning_chat.md`. The student reviews the plan in a fresh build chat at prompt P1 before any code is written.*

## Conflicts resolved

| Conflict | Decision | Why |
|---|---|---|
| Stage 2 schema: one list per category (D1/D3) or a flat `facts` list (D2) | Flat `facts[]` with `id` (F1..), `category` and `quote` | IDs are easier to link in later stages, there is one filter loop, and the handbook categories stay as an enum |
| Contradiction quotes: `quote`+`quote_b` (D1) or `quotes[]` (D2) | `quote` + `quote_b` | Code can require both quotes to be verified, in different sentences, and not nested |
| Labels: `TASK-001 needs-clarification` (D1/D2) or `TASK-001` only (D3) | `TASK-001` only | The 5 columns are fixed and Jira labels cannot contain spaces. Status goes in the Description |
| Epic acceptance criteria: `* None (epic)` (D3) or no section | Every ticket keeps the field, so the format is the same for all. For epics, `acceptance_criteria: []`, and the CSV has `h3. Acceptance Criteria` followed by the non-bullet line `Not applicable (epic) - see child tickets TASK-002, TASK-003` | The field is present on every ticket. A non-bullet line means `parse_ac` returns `[]`, so Track A still refuses to merge |
| Mapping RC3 keys back: by row order (D2) or by label (D3) | By label (`TASK-00x`), checked after import | Jira does not promise to keep import row order |
| Stage 5 tickets | Plain code, no LLM (all drafts agree) | The step is a mechanical transform, so there is nothing for an LLM to invent |
| Number of prompts: 13 (D3) or 7 (D2) | 8: P1 review, P2 to P6 one stage each, P7 review plus edge cases, P8 README | Still one stage per prompt, and it fits the time plan in section 9 |
| Deadline "as soon as possible" | A deadline value is kept only if its verified quote contains a concrete date or number. Otherwise it is "Not specified" and a question is raised | "ASAP" is not a deadline |

---

## 1. Goal and what is marked

**Goal:** a Python CLI that takes a raw brief file and produces three things:
- a structured breakdown;
- Jira-style tickets;
- open questions.

All three are shown **in full on screen** and saved as JSON and a Jira CSV. A Markdown report is optional. The tool must never assume anything (handbook lines 37 and 93).

**Marking:** Task 1 is worth 20 marks, and the exported chats are "the main item that will be marked". Missing, edited or fabricated chats earn no marks.

| Parameter (marks) | Evidence to produce |
|---|---|
| Planning 15% (3) | `PLAN.md` (max 1 page) states that it was drafted with AI help in `chats/00_planning_chat.md`. It is pasted and reviewed in prompt P1, and the accepted or rejected changes are recorded |
| Approach 25% (5) | Prompts P2 to P6 each cover one stage and have role, context, rules and a JSON schema. Each stage takes the **verified** output of the stage before it. The golden rule, including "write Not specified AND raise a question", is visible in the prompts |
| Correctness 30% (6) | `out/clear/` and `out/vague/` contain the full ticket fields, unique IDs, verified quotes, correct status and a Jira CSV |
| Testing 20% (4) | `TESTING.md` with pass/fail for each check, plus at least 2 real defects pasted back into the build chat and fixed. The rejected-items log is part of this |
| Evidence 10% (2) | Both chats exported unedited (`chats/00_planning_chat.md` and `chats/01_build_chat.md`), README, both briefs, and `out/*/run.log` |

## 2. Architecture

```
brief.txt
  │
  ▼
[1 INPUT] code ─ load, strip BOM, refuse empty, split into S1..Sn sentences
  │
  ▼
[2 UNDERSTAND] LLM ─► facts JSON ─► code: quote_ok filter ─► verified facts + rejected[]
  │
  ▼
[3 GAPS] LLM(brief + verified facts) ─► questions JSON ─► code: quote check, contradiction
  │                                         check (different sentences, not nested), strip bad
  │                                         links, missing_info_scan() templates
  ▼
[4 BREAK DOWN] LLM(brief + facts + questions) ─► epics/tasks JSON ─► code: drop unverified AC/deps/
  │                                         priority/estimate/deadline, reject tasks with no
  │                                         valid source facts, invention_lint() + content-word lint
  ▼
[5 TICKETS] code only ─ TASK-001.., remap deps, link questions, "Not specified", status
  │
  ▼
[6 OUTPUT] code only ─ full tickets + questions on console (tee to run.log) + tickets.json
                       + tickets_jira.csv  [+ report.md, optional]
```

```
task1/
  PLAN.md  TESTING.md  README.md
  chats/00_planning_chat.md  chats/01_build_chat.md
  main.py       # CLI: python main.py briefs\vague.txt --out out\vague [--model gemini-2.5-flash]
  llm.py        # call_json(system, user, model, max_tokens) -> dict
  prompts.py    # GOLDEN_RULE, UNDERSTAND, GAPS, BREAKDOWN
  verify.py     # normalise, quote_ok, sentence_of, filter_facts, check_questions,
                #   filter_breakdown, missing_info_scan, invention_lint, content_word_lint
  tickets.py    # build_tickets()  (no LLM)
  export.py     # print_console, to_json, to_csv, parse_ac [, to_markdown]
  briefs/clear.txt  briefs/vague.txt
  tests/test_verify.py  tests/test_export.py  tests/edge/empty.txt  tests/edge/short.txt
  out/clear/  out/vague/
```

**What the LLM does:** it proposes facts (Stage 2), questions (Stage 3), and epics, tasks and acceptance criteria (Stage 4). That is 3 calls per run, each returning strict JSON.

**What plain code does:**
- loads the brief;
- verifies quotes and rejects items that fail;
- checks contradictions;
- adds templated questions for missing information;
- runs both lints;
- assigns IDs, remaps dependencies and links questions;
- fills "Not specified" defaults and sets status;
- writes all output.

**`llm.py` rules (Google Gemini, free tier):**
- Library: `pip install google-genai`. The key comes only from `os.environ.get("GEMINI_API_KEY")`. If it is missing, print `ERROR: GEMINI_API_KEY not set` and exit with code 2.
- The model comes from the `GEMINI_MODEL` env var or `--model`, defaulting to `gemini-2.5-flash` (free tier). If AI Studio lists a newer Flash model, pass its name; no code change is needed.
- One function: `call_json(system, user, model, max_tokens)`:
```python
from google import genai
from google.genai import types
client = genai.Client()                      # reads GEMINI_API_KEY
resp = client.models.generate_content(
    model=model, contents=user,
    config=types.GenerateContentConfig(
        system_instruction=system,
        response_mime_type="application/json",   # JSON mode
        temperature=0,
        max_output_tokens=max_tokens))
```
- Set `max_output_tokens` explicitly: **8192** for Stages 2 and 3, **16384** for Stage 4. On 2.5 models, "thinking" tokens count toward this limit. If replies come back empty or cut off, add `thinking_config=types.ThinkingConfig(thinking_budget=0)`. Paste the real error into the chat first, because that counts as test evidence.
- If `resp.candidates[0].finish_reason` is `MAX_TOKENS`, or `resp.text` is empty, raise `StageError("output truncated")`. Do **not** retry the parse.
- Strip ```` ``` ```` fences from `resp.text` and run `json.loads`. If that fails, retry once with `"Your previous reply was not valid JSON: <err>. Return ONLY the JSON."`.
- If the retry also fails, save the raw reply to `out/<run>/failed_<stage>.txt`, exit with code 3, and write no partial export.
- Free-tier rate limit: on HTTP 429 (`RESOURCE_EXHAUSTED`), wait 30 s and retry once, then fail with a clear message. A run makes only 3 calls.

## 3. Stage-by-stage spec

**Shared `GOLDEN_RULE` block, prepended to all three system prompts:**
```
GOLDEN RULE - NEVER ASSUME.
- Use ONLY information written in the BRIEF. Do not add features, technologies, providers,
  priorities, estimates, deadlines, users or platforms.
- Every item MUST include "quote": an EXACT copy-pasted substring of the BRIEF (no paraphrase,
  no ellipsis, at least a few words). Items without a verbatim quote will be deleted by code.
- When the brief is silent, write null / "Not specified" AND add an open question (Stage 3)
  or a blocked_by_question_ids link (Stage 4). Never guess. An empty list is correct.
- Return ONLY valid JSON matching the schema. No prose, no markdown fences.
```

**`verify.py` core:**
```python
def normalise(s):
    for a, b in {"\u2018":"'","\u2019":"'","\u201c":'"',"\u201d":'"',"\u2013":"-","\u2014":"-"}.items():
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", s).strip().lower().rstrip(".")
def quote_ok(q, brief):
    return bool(q) and len(normalise(q)) >= 8 and normalise(q) in normalise(brief)
def sentence_of(q, sentences):          # -> "S7" or None
    return next((s["sid"] for s in sentences if normalise(q) in normalise(s["text"])), None)
```

### Stage 1: Input (code)
- **Input:** a file path.
- **Output:** `brief` (str) and `sentences` (`[{"sid":"S1","text":...}]`).
- **Rules:**
  - Read the file as UTF-8 and strip the BOM.
  - If the brief is empty or only whitespace, print `ERROR: brief is empty` and exit with code 1 **before any API call**.
  - Split sentences on `(?<=[.!?])\s+|\n+`.
- **Used for:** `source_reference = 'S7: "<quote>"'`, where S7 is the sentence that contains the quote.

### Stage 2: Understand (LLM, `UNDERSTAND`, max_output_tokens 8192)
- **Role:** "You are a requirements analyst. Extract only what the brief explicitly states."
- **Input:** the brief only.
- **Output:**
```json
{"facts":[{"id":"F1",
  "category":"goal|feature|user|constraint|integration|deadline|priority|estimate",
  "text":"short restatement using the brief's words","quote":"exact substring"}]}
```
- **Rules:**
  - Never infer users, platforms, technologies, integrations, priorities or dates.
  - Extract both sides of a contradiction. Do not resolve it.
- **Code checks:**
  - `filter_facts` keeps a fact only if `quote_ok` passes. Failed facts go to `rejected[]` as `{stage, item, reason:"quote not in brief"}`.
  - Duplicate IDs are renumbered.
  - The verified facts and the rejected list are printed.

### Stage 3: Detect gaps (LLM, `GAPS`, max_output_tokens 8192)
- **Role:** "You are a sceptical QA analyst / project manager who finds what a developer needs but the brief does not give."
- **Input:** the brief and the **verified** facts JSON.
- **Output:**
```json
{"questions":[{"id":"Q1",
  "category":"missing|vague|contradiction|undefined_term|scope_gap",
  "question":"one specific question the client can answer",
  "quote":"exact substring or null","quote_b":"second exact substring (contradiction only) or null",
  "related_fact_ids":["F3"]}]}
```
- **Rules in the prompt:**
  - **vague:** name the word and ask for a measurable target. Never suggest a number.
  - **contradiction:** `quote` and `quote_b` must come from two different sentences. Ask which one applies and never choose.
  - **undefined_term:** ask what the term is and what interface or API it exposes.
  - **scope_gap:** ask, and never add a feature.
  - **missing:** `quote` may be null only when something is absent from the whole brief, such as target users, platform, integrations, deadline or priorities.
  - Ask one question per issue, with no compound questions.
- **Code checks (`check_questions`):**
  - A non-null `quote` must pass `quote_ok`. Otherwise the question is rejected.
  - A `contradiction` needs both quotes to pass `quote_ok`. Then `sentence_of(quote) != sentence_of(quote_b)`, and neither normalised quote may contain the other. Otherwise the question is rejected with the reason `"contradiction quotes same sentence/nested"`.
  - Unknown `related_fact_ids` are removed.
- **`missing_info_scan()`** adds templated questions with no LLM call. It skips any template whose topic already has a question.

| Condition | Templated question |
|---|---|
| no `user` fact | "Who are the target users / user roles?" |
| no `deadline` fact whose quote has a digit | "What is the deadline or launch date?" |
| no verified fact quote (**any category**) matches `web\|mobile\|app\|ios\|android\|desktop\|browser` | "Which platform(s) must be supported?" |
| no `integration` fact | "Does the system need to integrate with any existing systems (payments, accounts, notifications)? If so, which?" |
| no `priority` fact | "Which features have the highest priority for the first release?" |

### Stage 4: Break down (LLM, `BREAKDOWN`, max_output_tokens 16384)
- **Role:** "You are a tech lead splitting verified requirements into small developer tasks."
- **Input:** the brief, the verified facts and the verified questions.
- **Output:**
```json
{"epics":[{"local_id":"E1","title":"","description":"","quote":"",
  "tasks":[{"local_id":"E1.T1","type":"Story|Task","title":"Verb-first summary",
    "description":"what and why, in the brief's words","source_fact_ids":["F3"],
    "acceptance_criteria":[{"text":"testable condition","quote":""}],
    "dependencies":[{"local_id":"E1.T2","quote":"sentence that states the link"}],
    "priority":{"value":null,"quote":null},"estimate":{"value":null,"quote":null},
    "deadline":{"value":null,"quote":null},
    "blocked_by_question_ids":["Q1"]}]}]}
```
- **Rules in the prompt:**
  - Every task comes from at least one verified fact.
  - Each acceptance criterion restates a brief sentence as a testable condition, uses the brief's words, and has a quote.
  - A dependency is allowed only when a quote states the link.
  - priority, estimate and deadline stay null unless the brief states them. When a field is null, link the matching open question in `blocked_by_question_ids`.
  - For contradicted items, create the task and link the contradiction question. Do not pick a side.
- **Code checks (`filter_breakdown`):**
  - A task with no verified fact in `source_fact_ids` is rejected as invented.
  - Acceptance criteria, dependencies, and priority/estimate/deadline values whose quote fails are dropped and logged.
  - A deadline needs a digit in its quote. Otherwise it becomes "Not specified".
  - A dropped dependency becomes the question `"Does <A title> depend on <B title>?"` with category `missing`.
  - A task with 0 acceptance criteria left gets the question `"What testable acceptance conditions apply to '<title>'?"`.
  - Acceptance-criteria text is cleaned: newlines become spaces, and a leading `h3.` or `*` is removed.
- **`invention_lint()`** scans titles, descriptions and acceptance criteria for denylist terms that do **not** appear in the brief, and prints `WARNING invented term: refund in TASK-004`.
  - Denylist: `stripe paypal react angular vue aws azure firebase oauth jwt sql postgres mongodb ios android kubernetes docker sms email push refund invoice currency waitlist "waiting list" notification login password dashboard`
  - Regex: `\d+\s?(ms|seconds?|%)`
- **`content_word_lint()`** prints `WARNING unsourced word 'refunds' in AC of TASK-004` for any word in an acceptance-criterion `text` that has 4 or more letters, is not a stopword, and does not appear in the brief or in that criterion's own quote. Compare lowercased words and strip a trailing `s`.
- **Lint warnings are pasted back into the chat as real errors.** P7 decides whether each one is a real invention or harmless wording.

### Stage 5: Generate tickets (code, `tickets.py`)
- **IDs:** walk the epics in order. Assign `TASK-001` to the first epic, then its tasks, then the next epic. Build a map from `local_id` to ticket ID and remap dependencies through it.
- **Open questions:** the union of `blocked_by_question_ids` and the questions whose `related_fact_ids` overlap the task's `source_fact_ids`. Questions are renumbered `Q-001..`.
- **Unlinked questions** (including the templated ones) are attached to every epic and also listed under "General questions", so they are never lost.
- **Defaults:** a null priority, estimate or deadline becomes `"Not specified"`.
- **Epics:** `acceptance_criteria: []`, and `children` lists the child ticket IDs.
- **Status:**
  - A task is `"Ready"` if it has no open questions. Otherwise it is `"Needs clarification"`.
  - An epic is `"Needs clarification"` if it or any of its children is.
- **Ticket record** (the same fields for every ticket):
```json
{"ticket_id":"TASK-002","title":"","type":"Story","parent":"TASK-001","children":[],
 "description":"","acceptance_criteria":[{"text":"","quote":""}],
 "source_reference":"S4: \"...\"","dependencies":["TASK-003"],
 "open_questions":[{"id":"Q-002","category":"vague","question":""}],
 "priority":"Not specified","estimate":"Not specified","deadline":"Not specified",
 "status":"Needs clarification"}
```

### Stage 6: Output (code, `export.py`)
- **Console (required, never cut).** Print in this order:
  1. Every ticket in full: ID, type, parent or children, title, description, source reference, dependencies, priority, estimate, deadline, status and open questions. Each acceptance criterion is printed as `- <text>   <- "<quote>"`, so P7 can check it against its quote. Epics print `Acceptance Criteria: Not applicable (epic) - see child tickets ...`.
  2. Every question, grouped by category. Contradictions show both quotes.
  3. Rejected items with their reasons, then lint warnings.
  4. Counts: facts, questions by category, tickets by status, rejected items.
- **`run.log`:** an exact copy of the console output (tee). This is the plain-text report.
- **`tickets.json`** and **`tickets_jira.csv`:** see section 4.
- **`report.md`:** optional. It has the same content as the console. It is the first item on the cut-list.

## 4. Ticket format, JSON export and Jira CSV, and how Track A uses them

**`tickets.json`:**
```json
{"brief_file":"briefs/vague.txt","model":"gemini-2.5-flash","generated_at":"ISO8601",
 "tickets":[...], "general_questions":[...], "rejected":[...], "lint_warnings":[...]}
```

**`tickets_jira.csv`:**
- Write it with `open(path, "w", newline="", encoding="utf-8")` and `csv.writer(f, quoting=csv.QUOTE_ALL)`. `newline=""` stops blank rows on Windows, and plain UTF-8 with no BOM keeps the BOM out of the "Summary" header.
- The columns are exactly `Summary,Issue Type,Description,Priority,Labels`.

| Column | Value |
|---|---|
| Summary | title |
| Issue Type | `Epic` / `Story` / `Task` |
| Description | template below (Jira wiki markup) |
| Priority | `Highest`, `High`, `Medium` or `Low` only if the brief's quoted word maps directly. Otherwise **blank**, meaning the tool supplies no value. **Note:** Jira's CSV importer gives a blank or unmapped Priority the project's default (usually Medium). The authoritative value is the `Priority: Not specified` text in the Description's `h3. Details` line. When importing, do not map the Priority column for rows where it is blank, or leave Priority unmapped |
| Labels | `TASK-002` (no spaces) |

**Description template, task or story.** The heading and the `* ` bullets must be exact.
```
{description}

h3. Acceptance Criteria
* {criterion 1 text}
* {criterion 2 text}

h3. Source
{quote}{source_reference}{quote}

h3. Dependencies
{TASK-003, ... | None stated in brief}

h3. Open Questions
* [Q-002] {question}      (or: None)

h3. Details
Status: Needs clarification | Parent: TASK-001 | Priority: Not specified | Estimate: Not specified | Deadline: Not specified
```

**Description template, epic.** It has the same sections. The Acceptance Criteria section has one line with no bullet:
```
h3. Acceptance Criteria
Not applicable (epic) - see child tickets TASK-002, TASK-003
```

**How Track A uses it:**
1. Import the CSV into a test Jira project with key RC3. Jira assigns RC3-1, RC3-2 and so on, and the `TASK-00x` label maps each key back to its source ticket.
2. A PR branch `feature/RC3-2-book-class` matches `([A-Z][A-Z0-9]+-\d+)`, which gives `RC3-2`.
3. The Story Fetcher calls `GET /rest/api/2/issue/RC3-2?fields=summary,description,labels`. **Use API v2**, because it returns the description as a wiki-markup string. v3 returns ADF JSON, so the fallback for v3 is to walk the ADF for the heading node.
4. The shared parser `export.parse_ac()` is also unit-tested in Task 1:
```python
def parse_ac(desc):
    m = re.search(r"h3\.\s*Acceptance Criteria\s*\n(.*?)(?=\nh3\.|\Z)", desc, re.S)
    return [l[2:].strip() for l in m.group(1).splitlines() if l.startswith("* ")] if m else []
```
5. If `parse_ac` returns `[]` (an epic's "Not applicable" line, or a task with no criteria), Track A must **not merge** and must report "ticket has no acceptance criteria". A `Needs clarification` status in the Description can also be treated as do-not-merge.

**Jira import notes for the README:**
- Epic rows: import into a **team-managed** project, or, in company-managed or Server projects, also map Summary to **Epic Name** for Epic rows. Otherwise the Epic rows fail or warn.
- The 5 fixed columns carry no parent link. Parent/child links exist only in the Description (`Parent:` and the epic's child list) and through the `TASK-00x` labels.

## 5. Prompt sequence for the build chat

**Key setup (do this first, in your OWN PowerShell window, not through Claude):**
- Get a free key at aistudio.google.com → Get API key.
- Run `setx GEMINI_API_KEY "your-key"`, then close and reopen your terminals and Claude Code.
- Never paste the key into the chat, never use `!` to set it, and never ask Claude to set it. The exported chat is submitted.
- Claude Code does not use `GEMINI_API_KEY`, so one window is enough. You can run `python main.py ...` yourself and paste the output into the chat.

Paste one prompt at a time. After each prompt, run the check. If anything is wrong, paste the **real** traceback or bad output and say what is wrong. During P2 to P6, run **clear.txt only**. vague.txt is run in P7.

**P1. Plan review (no code)**
> Role: you are a senior engineer reviewing a plan before any code is written.
> Context: I am building a Python CLI that turns a raw client brief into a task breakdown, Jira tickets and open questions. The golden rule is NEVER ASSUME: anything the brief doesn't state must become "Not specified" plus an open question, never a guess. My plan is in PLAN.md (read it). I drafted it with AI help in a separate planning chat, which I am submitting as chats/00_planning_chat.md. It has 6 stages; stages 2–4 are one LLM call each returning strict JSON, and everything else (quote verification, IDs, "Not specified", status, export) is plain Python.
> Rules: do NOT write code yet. Check the plan against these handbook requirements: [paste handbook lines 40–74]. List any requirement the plan misses, and any place where the LLM could still invent something.
> Output: a numbered list of gaps or risks, then "PLAN OK" or the required changes.

*Verify:* accept or reject each point yourself, update PLAN.md, and add a line "Changes after P1 review: ...". This is planning evidence.

**P2. LLM wrapper, verifier and offline tests**
> Role: senior Python engineer. Context: implement only `llm.py`, `verify.py` (normalise, quote_ok, sentence_of) and `tests/test_verify.py`, as specified in PLAN.md.
> Rules: Google Gemini via the `google-genai` SDK (`from google import genai`; `genai.Client()`; `client.models.generate_content(model=..., contents=user, config=types.GenerateContentConfig(system_instruction=system, response_mime_type="application/json", temperature=0, max_output_tokens=...))`). Read the key ONLY from env var GEMINI_API_KEY; if missing, print a clear error and exit 2. Model from GEMINI_MODEL env var or a parameter, default gemini-2.5-flash. max_output_tokens 8192 default, 16384 for Stage 4. If finish_reason is MAX_TOKENS or resp.text is empty, raise StageError("output truncated") without retrying. On HTTP 429, wait 30 s and retry once. Otherwise `call_json(system, user, model, max_tokens)` strips code fences, runs json.loads, retries once with the parse error, and on a second failure saves the raw text and raises StageError. quote_ok requires a normalised substring of at least 8 characters. Tests (no API): exact match, curly quotes, extra whitespace, paraphrase fails, ellipsis fails, 1-word quote fails, sentence_of finds the right sentence.
> Output: the files and the commands to run.

*Verify:*
- `pytest -q` passes.
- `python -c "from llm import call_json; print(call_json('Return JSON {\"ok\": true}','go','gemini-2.5-flash', 256))"` prints `{'ok': True}`.
- Missing-key case, without touching the real variable: `cmd /c "set GEMINI_API_KEY=&& python main.py briefs\clear.txt"` should exit cleanly with code 2 (`echo $LASTEXITCODE`). If `main.py` does not exist yet, run this check after P3.

**P3. Stages 1 and 2: Input and Understand**
> Role: requirements analyst plus Python engineer. Context: implement load_brief (Stage 1) and understand(brief) (Stage 2) exactly as in PLAN.md §3, plus `filter_facts` in verify.py, and wire them into main.py so it prints the verified facts and the rejected list.
> Rules: system prompt = GOLDEN_RULE + "Extract ONLY what the brief explicitly states…". GOLDEN_RULE must include: "When the brief is silent, write null / 'Not specified' AND add an open question (Stage 3) or a blocked_by link (Stage 4)." Output schema: [paste the Stage 2 JSON]. Python, not the LLM, drops facts whose quote fails and logs them in rejected[]. An empty brief exits with code 1 before any API call.
> Output: code changes and the run command.

*Verify (clear.txt):*
- Ctrl+F 3 quotes in the brief and confirm all are found.
- Hand-edit one saved quote, re-run the filter, and confirm it is rejected. Paste that result into the chat.
- `python main.py tests\edge\empty.txt` exits with code 1 and makes no API call.

**P4. Stage 3: Gaps**
> Role: sceptical project manager. Context: implement detect_gaps(brief, verified_facts), check_questions and missing_info_scan in verify.py, per PLAN.md §3 Stage 3. Input is ONLY the brief and the VERIFIED facts.
> Rules: GOLDEN_RULE (including "write Not specified AND raise a question") is prepended. 5 categories; a vague question names the word and asks for a measurable target without suggesting one; a contradiction needs quote AND quote_b from different sentences and asks which applies; a scope gap ASKS and never adds; one specific, answerable question each, with related_fact_ids. Code rejects failed quotes, and rejects contradictions whose quotes sit in the same Stage 1 sentence or where one quote contains the other. missing_info_scan adds templates for users, deadline, platform (regex over ALL verified fact quotes), integrations and priorities, skipping any topic already asked.
> Output schema: [paste the Stage 3 JSON]. Print questions grouped by category.

*Verify (clear.txt):*
- There is **no** "Which platform?" question, because "desktop and mobile browsers" is quoted.
- The integration question appears.
- There is no deadline question.
- There is no priority question.
- Add one unit test showing that the contradiction pair `"web only"` / `"want web only"` is rejected.

**P5. Stage 4: Break down**
> Role: tech lead. Context: implement break_down(brief, facts, questions) with max_output_tokens 16384, plus filter_breakdown, invention_lint and content_word_lint per PLAN.md §3 Stage 4.
> Rules: GOLDEN_RULE prepended; when a field is unstated it stays null AND the task links the matching question in blocked_by_question_ids. Tasks only from verified facts; every acceptance criterion uses the brief's words and has a verbatim quote; dependencies only with a quote stating the link, otherwise code turns them into "Does A depend on B?" questions; priority, estimate and deadline stay null unless stated (a deadline needs a digit); for contradictions, create the task and link the question without choosing a side. Code rejects tasks with no valid source facts, drops unverified fields, and prints denylist and unsourced-word warnings.
> Output schema: [paste the Stage 4 JSON].

*Verify (clear.txt):*
- Every task has at least 1 acceptance criterion, each printed beside its quote.
- Paste every lint warning back into the chat as an error and decide with Claude whether it is a real invention.

**Fix loop (reserved 5 minutes).** Use it for the first real failure, such as a truncated output, a rejected quote, or a false platform question. Paste the exact output, get the fix, and re-run. This is defect #1 for TESTING.md.

**P6. Stages 5 and 6: Tickets and export**
> Role: Python engineer. Context: implement tickets.py build_tickets and export.py (print_console, to_json, to_csv, parse_ac) exactly per PLAN.md §3 Stages 5–6 and §4. No LLM calls.
> Rules: TASK-001.. in epic-then-task order; remap dependencies; union question links; unlinked questions go to every epic and to "General questions"; "Not specified" defaults; status logic. The same fields on every ticket; epics get acceptance_criteria [] and, in the CSV, "h3. Acceptance Criteria" followed by "Not applicable (epic) - see child tickets ...". Console prints EVERY ticket in full (each AC beside its quote), then questions grouped by category, then rejected items, warnings and counts; tee everything to run.log. CSV columns exactly `Summary,Issue Type,Description,Priority,Labels`, QUOTE_ALL, newline="", utf-8; Priority blank unless stated; Labels = ticket ID; the exact Description template. Add a test that re-reads the CSV with csv.DictReader and recovers every task criterion with parse_ac, while epics return [].
> Output: code, tests, and the run command.

*Verify (clear.txt):*
- `pytest` passes.
- The CSV headers are exact, and IDs are sequential and unique.
- Some tasks are `Ready`. Every dependency points to an existing ID.
- Check for invented terms in the outputs only:
  `Select-String -Pattern "stripe|paypal|refund|invoice|currency|waitlist|notification|login|password|dashboard|seconds|%" -Path out\clear\tickets.json, out\clear\tickets_jira.csv`
  Every hit must also appear in the brief.

**P7. vague.txt run, line-by-line review and edge cases**
> Role: strict reviewer. Here are both briefs: [paste]. Here is the full run.log for each: [paste out\clear\run.log and out\vague\run.log]. Compare every ticket, acceptance criterion (shown beside its quote) and question with the brief line by line. List (a) any detail not in the brief, (b) any gap not raised — check the 8 traps in PLAN.md §6, (c) any wrong status, field or link. Then fix the CODE or PROMPTS, never the output files. Also give me the commands for these edge cases (robustness only, no new features): empty brief, the one-line brief "Build an app.", and the missing API key via `cmd /c "set GEMINI_API_KEY=&& python main.py briefs\clear.txt"`. I will run them and paste the results.

*Verify:*
- Paste at least 1 defect that **you** found yourself (defect #2). Re-run both briefs and save the final `out/clear` and `out/vague`.
- Re-run the P6 `Select-String` against `out\vague\tickets.json, out\vague\tickets_jira.csv`.
- Fill in `TESTING.md`.

**P8. README**
> Write README.md: what the tool does plus the 6-stage diagram; libraries (Python 3.10+, google-genai, pytest); key setup with `setx GEMINI_API_KEY` in your own terminal (never in code, never in the chat; free key from Google AI Studio); run commands incl. `--model`; outputs; Jira CSV import steps (team-managed project or Summary→Epic Name for epics; blank Priority receives Jira's default on import so leave it unmapped — the authoritative value is in h3. Details; parent links only in Description and TASK-00x labels); the `h3. Acceptance Criteria` contract for Track A; "How it avoids assumptions"; a test summary linking TESTING.md; known limits; a deliverables index; and a "How this was built" note: plan drafted with AI help in chats/00_planning_chat.md, reviewed in P1 of chats/01_build_chat.md.

*Verify:* every claim in the README matches the code.

## 6. Two demo briefs

**`briefs/clear.txt`** (about 170 words)
```
FitLane Gym - Class Booking Web App

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
```

*Expected result:*
- About 2 epics and 5 to 7 tickets, with most tasks **Ready**.
- Priority is `High` or `Low` only where the brief states it.
- Deadline is `15 March 2027`.
- One quoted dependency: booking depends on class creation.
- There is no platform, users, deadline or priority question.

*Honest remaining questions:*
- the confirmation channel (scope gap; the tool must not choose email or SMS);
- whether a freed place goes to a waiting list;
- the templated integrations question (general, attached to the epics).

**`briefs/vague.txt`** (about 150 words)
```
Hi team,

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
```

**Traps, and what the tool must do:**

| # | Trap | Expected question | Must not |
|---|---|---|---|
| 1 | "App Store and Google Play" vs "web only" | contradiction with both quotes from different sentences: "which applies for v1?" | pick a platform |
| 2 | "fast, modern and secure" | 3 vague questions asking for measurable targets | invent "<2s load" or "OAuth" |
| 3 | "ORMS" | undefined_term: what it is and what API it exposes | assume an ERP or REST |
| 4 | "loyalty scheme to work like last time" | undefined_term: what the earlier rules were | invent points rules |
| 5 | "pay online" | scope_gap: payment methods, currency, refunds? | add Stripe, refunds or invoices |
| 6 | "Delivery slots" | scope_gap: slot length, capacity, cut-off? | invent slot rules |
| 7 | "the usual reports" | vague: which reports, which fields | invent report content or a dashboard |
| 8 | "as soon as possible", no ranking of features | missing deadline (template) and priorities (template, or a vague question on "important" if it was extracted as a priority fact); fields say "Not specified" | invent a date or a priority |

*Expected result:* most tickets are **Needs clarification**, there are 8 or more questions, and each question is linked to the TASK IDs it blocks.

## 7. Testing and review checklist (`TESTING.md`)

| # | Check | Expected |
|---|---|---|
| T1 | Unit tests for quote_ok (exact, curly quotes, whitespace, paraphrase, ellipsis, 1-word) and sentence_of | all pass |
| T2 | Contradiction with 1 quote, the same quote twice, a nested quote ("web only" / "want web only"), or both quotes in one sentence | rejected |
| T3 | Every acceptance criterion and source printed next to its quote on screen | 100% verified |
| T4 | Invented-detail hunt: denylist lint, content-word lint, and `Select-String` on tickets.json and tickets_jira.csv only | 0 terms that are not in the brief |
| T5 | Priority, Estimate and Deadline match the brief or say "Not specified"; CSV Priority is blank when not stated | pass |
| T6 | The 8 traps in vague.txt give questions of the right category | 8/8 |
| T7 | clear.txt: most tasks Ready, deadline 15 March 2027, 1 quoted dependency, no false platform question | pass |
| T8 | Status logic: questions make a ticket Needs clarification, and an epic inherits from its children | pass |
| T9 | Unique IDs, no dangling dependencies, no lost questions | pass |
| T10 | CSV round-trip: DictReader plus parse_ac recovers every task criterion; epics have the AC heading and return [] | pass |
| T11 | Empty or whitespace-only brief | exit 1 before any API call |
| T12 | "Build an app." | at most 1 epic, mostly questions, no invented features |
| T13 | Key unset via `cmd /c "set GEMINI_API_KEY=&& python main.py briefs\clear.txt"` | exit 2, clear message, no traceback |
| T14 | Manual: Ctrl+F 5 random quotes in the brief | all found |

*Not tested, listed honestly in TESTING.md:* broken-JSON retry, `MAX_TOKENS` truncation (unless it happens for real), and non-English briefs.

Log at least 2 real defects with the time and the fix. The rejected-items log and the lint warnings count as evidence.

## 8. Deliverables and README outline

**Deliverables:**
- [ ] `chats/00_planning_chat.md`: this planning conversation, exported **complete and unedited**
- [ ] `chats/01_build_chat.md`: the Claude Code build chat, exported **complete and unedited**
- [ ] Source code: `main.py llm.py prompts.py verify.py tickets.py export.py tests/`
- [ ] `PLAN.md`, which states it was drafted with AI help (chat 00) and reviewed in P1; `TESTING.md`; `README.md`
- [ ] `briefs/clear.txt`, `briefs/vague.txt`
- [ ] `out/clear/` and `out/vague/`, each with `run.log`, `tickets.json` and `tickets_jira.csv`. `report.md` is optional
- [ ] No API key in any file or chat export. This searches for your real key value without printing it, and must print `0` (it also covers `chats/`): `$k=[Environment]::GetEnvironmentVariable('GEMINI_API_KEY','User'); (Get-ChildItem -Recurse -File | Select-String -SimpleMatch -Pattern $k).Count`. Your key starts with `AQ.`, so a prefix search for `AIza` would not catch it.

**README outline:**
1. Purpose and the 6-stage diagram (LLM vs code).
2. Requirements: Python 3.10+, `pip install google-genai pytest`.
3. Key setup: free Gemini key from Google AI Studio; `setx GEMINI_API_KEY "..."` in your own terminal. The key is never in code or chat.
4. Run: `python main.py briefs\vague.txt --out out\vague [--model gemini-2.5-flash]`.
5. Outputs and Jira CSV import:
   - column mapping;
   - a blank Priority means the tool supplied no value, but Jira applies its default on import, so leave Priority unmapped for those rows; `Priority: Not specified` in `h3. Details` is authoritative;
   - Epic rows need a team-managed project or Summary mapped to Epic Name;
   - parent links are only in the Description and the `TASK-00x` labels.
6. **How it avoids assumptions:**
   - the golden rule ("Not specified" plus a question) is in every prompt;
   - code verifies every quote and logs rejections;
   - contradictions need two quotes from different sentences;
   - missing users, platform, integrations, deadline and priorities are raised from templates;
   - the denylist and content-word lints run on the output;
   - "Not specified" defaults and status are set by code;
   - dependencies are kept only when quoted.
7. The Track A contract: `h3. Acceptance Criteria`, `* ` bullets, the epic "Not applicable" line, the `TASK-00x` label, the v2 API, and no acceptance criteria meaning no merge.
8. Test summary and known limits: long briefs, normalisation of non-Latin text, lint false positives, and Jira Epic and Priority import behaviour.
9. How this was built: chat 00 (planning) and chat 01 (build, one stage per prompt).
10. Deliverables index.

## 9. Time plan (about 55 minutes of work) and cut-list

Realistic work is 50 to 55 minutes. The default cuts are **already applied**: no `--simulate-bad-json`, no non-English test, edge cases merged into P7, plain-text `run.log` as the report, and clear.txt only during development. If only 40 minutes are left, apply the cut-list below in order straight away.

| Min | Activity |
|---|---|
| 0–5 | Create `task1/`, save both briefs, set GEMINI_API_KEY with setx and reopen terminals, start a new Claude Code chat, write PLAN.md from the template below |
| 5–7 | P1 plan review, then update PLAN.md |
| 7–13 | P2 wrapper, verifier, tests |
| 13–19 | P3 Input and Understand (clear.txt) |
| 19–25 | P4 Gaps (clear.txt) |
| 25–32 | P5 Break down (clear.txt) |
| 32–37 | **Reserved live fix loop** (defect #1) |
| 37–43 | P6 Tickets and export (clear.txt) |
| 43–49 | P7 vague.txt run, review, edge cases, TESTING.md (defect #2) |
| 49–52 | P8 README |
| 52–55 | Export chat 00 and chat 01 unedited, run the key-value search (section 8) over everything including `chats/`, zip |

**PLAN.md template (max 1 page):**
```
# PLAN - Brief2Jira (Task 1)
Drafted with AI help in chats/00_planning_chat.md; reviewed in P1 of chats/01_build_chat.md.
Goal: brief file -> breakdown + Jira tickets + open questions, never assuming.
Stages: 1 Input (code) | 2 Understand (LLM) | 3 Gaps (LLM) | 4 Break down (LLM) | 5 Tickets (code) | 6 Output (code)
LLM vs code: LLM proposes facts/questions/tasks as strict JSON; code verifies every quote,
  rejects + logs failures, adds missing-info questions, lints inventions, assigns TASK-001..,
  sets "Not specified" and status, exports CSV/JSON.
Ticket fields: ID, title, type, description, acceptance criteria, source reference,
  dependencies, open questions, priority/estimate/deadline (or Not specified), status.
Jira CSV: Summary, Issue Type, Description (h3. Acceptance Criteria + "* "), Priority, Labels=TASK-00x.
Tests: see TESTING.md (quote checks, 8 traps, status, CSV round-trip, edge cases).
Demo briefs: clear.txt (gym booking), vague.txt (grocery app with 8 traps).
Changes after P1 review: ...
```

**Cut-list, in order, if running late:**
1. The separate `report.md` file. The console and `run.log` still show every ticket and question in full, and that is never cut.
2. The `invention_lint` regex. Keep the denylist and the content-word lint.
3. Dependency extraction: send every dependency to open questions.
4. A short README (sections 3, 4, 6, 7 and 9 only).
5. Merge P1 into P2. Still paste PLAN.md first.

**Never cut:**
- one prompt per stage;
- quote verification and the rejected log;
- "Not specified" and status set by code;
- full tickets and questions printed on screen;
- the `h3. Acceptance Criteria` and `* ` CSV format with the `TASK-00x` label;
- both demo briefs with their outputs;
- at least 2 real errors reported back in the chat;
- both chats (planning and build) exported unedited.