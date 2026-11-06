# Brief2Jira (RC3 Task 1)

A Python CLI that turns a raw client brief (a text file) into:

- a structured breakdown (verified facts, epics and tasks),
- Jira-style tickets (`TASK-001`, `TASK-002`, ...),
- open questions for the client.

Everything is printed in full on screen and saved as JSON and a Jira-importable CSV.
The rule the tool follows is **never assume**: anything the brief does not state becomes
`Not specified` **and** an open question, never a guess.

## How it works: 6 stages

```
brief.txt
  |
  v
[1 INPUT]       code  load UTF-8, strip BOM, refuse empty (exit 1), re-join wrapped lines,
  |                   split into sentences S1..Sn
  v
[2 UNDERSTAND]  LLM   facts JSON  -> code: keep only facts whose quote is in the brief
  |
  v
[3 GAPS]        LLM   questions JSON -> code: verify quotes, contradiction check
  |                   (2 quotes, different sentences, not nested), strip "e.g." hints,
  |                   + templated questions for missing users/deadline/platform/integrations/priorities
  v
[4 BREAK DOWN]  LLM   epics/tasks JSON -> code: drop unquoted AC, dependencies, priority,
  |                   estimate, deadline; reject tasks with no verified source fact;
  |                   dropped items become questions
  v
[5 TICKETS]     code  TASK-001.., remap dependencies, link questions, "Not specified",
  |                   status (Ready / Needs clarification), lints for invented words
  v
[6 OUTPUT]      code  full console report (= run.log), tickets.json, tickets_jira.csv
```

The LLM (Google Gemini, JSON mode, temperature 0) is called 3 times per run and only
*proposes*. Plain Python verifies, numbers, links, defaults and exports.

| File | Role |
|---|---|
| `main.py` | CLI and pipeline (Stages 1-6), tees console output to `run.log` |
| `llm.py` | `call_json()` Gemini wrapper: JSON mode, retries, `StageError` |
| `prompts.py` | `GOLDEN_RULE`, `UNDERSTAND`, `GAPS`, `BREAKDOWN` system prompts and user-message builders |
| `verify.py` | quote checks, fact / question / breakdown filters, missing-info templates, lints |
| `tickets.py` | `build_tickets()` (no LLM) |
| `export.py` | console report, `tickets.json`, `tickets_jira.csv`, `parse_ac()` |
| `tests/` | 80 offline pytest tests + edge-case briefs in `tests/edge/` |

## Requirements

- Python 3.10+ (built and tested on Python 3.12)
- `pip install google-genai pytest`

## API key setup

1. Get a free key at Google AI Studio (aistudio.google.com -> Get API key).
2. In **your own** PowerShell window (not through Claude, not in a chat):
   ```powershell
   setx GEMINI_API_KEY "your-key"
   ```
3. Close and reopen your terminals.

The key is read only from the `GEMINI_API_KEY` environment variable. It is never in code,
in output files or in the chat exports. If it is missing the tool prints
`ERROR: GEMINI_API_KEY not set` and exits with code 2.

## Run

```powershell
python main.py briefs\clear.txt                     # output goes to out\clear
python main.py briefs\vague.txt --out out\vague
python main.py briefs\vague.txt --out out\vague --model gemini-3-flash-preview
```

- `--out DIR`: output folder (default `out/<brief file name without extension>`).
- `--model M`: Gemini model. Default: the `GEMINI_MODEL` environment variable (or `.env`), else `gemini-flash-lite-latest`.
  The demo outputs were made with `--model gemini-3-flash-preview` and `GEMINI_THINKING_BUDGET=1024`,
  which gave better task titles than the lite model (defects_log.md D32).
- Optional `GEMINI_THINKING_BUDGET` environment variable (e.g. `1024`) caps "thinking" tokens.
  Use it if a model returns `output truncated (finish_reason=MAX_TOKENS ...)`.

Exit codes: `0` success; `1` empty / unreadable brief or usage error (before any API call);
`2` `GEMINI_API_KEY` not set; `3` a stage failed (API error after one retry, truncated output,
invalid JSON twice). On exit 3 nothing is exported: the error goes to `failed_run.log`, and any
earlier successful `run.log`, `tickets.json` and `tickets_jira.csv` in that folder are left unchanged.

Free tier: a 429 or 503 waits 30 s and retries once; a daily-quota 429 fails at once.

Tests (offline, no key needed): `python -m pytest -q`

## Outputs

Each run writes to the output folder:

| File | Content |
|---|---|
| `failed_run.log` | Only after a failed run (exit 3): the console up to the error. Removed by the next successful run |
| `run.log` | Exact copy of the console: sentences, verified facts, questions grouped by category, epics/tasks, every ticket in full (each acceptance criterion beside its quote), all questions with linked tickets, rejected items with reasons, lint warnings, counts |
| `tickets.json` | `brief_file`, `model`, `generated_at`, `tickets`, `general_questions`, `questions`, `rejected`, `lint_warnings` |
| `tickets_jira.csv` | Jira import file (below) |

Every ticket has the same fields: `ticket_id, title, type, parent, children, description,
acceptance_criteria [{text, quote}], source_reference ('S6: "quote"'), dependencies,
open_questions, priority, estimate, deadline, status`.

Saved runs: `out/clear/`, `out/vague/`, `out/edge_short/` ("Build an app."), and the failed or
earlier iterations in `out/iterations/`.

## Jira CSV import

Columns, exactly: `Summary, Issue Type, Description, Priority, Labels` (UTF-8, no BOM, all fields quoted).

| Column | Value |
|---|---|
| Summary | ticket title |
| Issue Type | `Epic`, `Story` or `Task` |
| Description | Jira wiki markup: description, `h3. Acceptance Criteria` with `* ` bullets, `h3. Source`, `h3. Dependencies`, `h3. Open Questions`, `h3. Details` (Status, Parent, Priority, Estimate, Deadline) |
| Priority | `Highest` / `High` / `Medium` / `Low` only when the brief states it, otherwise blank |
| Labels | the ticket ID, e.g. `TASK-002` |

Import notes:
- **Epic rows:** import into a **team-managed** project, or in a company-managed / Server project
  also map Summary to **Epic Name** for Epic rows, otherwise those rows fail or warn.
- **Blank Priority** means the tool supplied no value, but Jira gives a blank Priority the project
  default (usually Medium). Leave Priority unmapped for those rows. The authoritative value is
  `Priority: ...` in the `h3. Details` line.
- **Parent links** are not in the 5 columns. They exist only in the Description (`Parent:` and the
  epic's child list) and through the `TASK-00x` labels.
- Jira keys (RC3-1, RC3-2, ...) are mapped back to tickets by the `TASK-00x` label, not by row order.

The real CSV import was not tested against a Jira instance (see TESTING.md).

## Track A contract

- Acceptance criteria live under the exact heading `h3. Acceptance Criteria`, one per line
  starting with `* `.
- An epic has the non-bullet line `Not applicable (epic) - see child tickets TASK-002, ...`;
  a task with no criteria has `None stated in brief`. Both parse to `[]`.
- Read the issue with Jira REST **API v2** (`GET /rest/api/2/issue/RC3-2?fields=summary,description,labels`),
  which returns the description as wiki markup. (v3 returns ADF JSON.)
- Parse with the shared function in `export.py`:
  ```python
  def parse_ac(desc):
      m = re.search(r"h3\.\s*Acceptance Criteria\s*\n(.*?)(?=\nh3\.|\Z)", desc, re.S)
      return [l[2:].strip() for l in m.group(1).splitlines() if l.startswith("* ")] if m else []
  ```
- `parse_ac` returning `[]` means **do not merge** ("ticket has no acceptance criteria").
  `Status: Needs clarification` in `h3. Details` can also be treated as do-not-merge.

## How it avoids assumptions

- **Golden rule in every prompt:** `GOLDEN_RULE` is prepended to all three system prompts: use only
  the brief, quote it verbatim, and when the brief is silent write null / "Not specified" AND raise
  a question.
- **Every quote is verified by code** (`verify.quote_ok`: normalised substring of the brief, at
  least 8 characters). Facts, questions, acceptance criteria, dependencies and field values with a
  failing quote are dropped and logged in `rejected` with a reason.
- **Values must be in their quote:** a priority needs a priority word, a deadline needs a digit, and
  the value itself must appear in its quote. A priority quote must also name the task it is put on
  ("Booking and cancellation are high priority" cannot make a login task High). "As soon as possible" is not a deadline.
- **Contradictions** need two verified quotes from different sentences, neither inside the other.
  Acceptance criteria that quote one side are dropped, and words found on only one side are
  passed to Stage 4 to avoid and linted afterwards.
- **Missing information** (users, deadline, platform, integrations, priorities) is raised from
  code templates when no fact covers it.
- **Questions never suggest answers:** `(e.g. ...)` / `such as ...` hints are stripped and logged.
- **Tasks need a verified source fact.** A task built only from user/priority/deadline facts and no
  verified acceptance criterion is rejected as invented.
- **Dependencies are kept only when quoted**; a dropped one becomes a "Does A depend on B?" question.
- **Lints on the final tickets:** a denylist of commonly invented terms (Stripe, OAuth, refund,
  dashboard, notification, ...) plus a number/unit regex, a content-word lint for words not in the
  brief, and a contradiction-side lint. Descriptions with an invented denylist term are replaced
  with neutral code-built text.
- **"Not specified" defaults, IDs and status are set by code**, never by the LLM.

## Test summary

80 offline tests pass (`python -m pytest -q`). Checklist T1-T14 from the plan: 12 PASS,
2 PARTIAL (content-word lint is not zero; 6 of 8 vague.txt traps get the exact expected
category, all 8 are raised), 0 FAIL. 32 real defects were found and handled during the build.
Details, evidence and the "Not tested" list: [TESTING.md](TESTING.md) and [defects_log.md](defects_log.md).

## Known limits

- Output depends on the model: all final demo outputs used `gemini-3-flash-preview`; the lite
  model gave weaker titles and missed the payment question (D32), and another model may split
  tasks or classify questions differently. Free-tier quota and 503 "high demand" errors can stop a run (exit 3).
- Some gaps can still be missed (e.g. clear.txt gets no "does a freed place go to a waiting list?"
  question) or get a different category than expected (vague payment question is `missing`).
- The content-word lint gives harmless paraphrase warnings (e.g. `select`, `weekly`); a human
  must review them.
- Sentence splitting re-joins hard-wrapped lines with a heuristic; a short line (6 words or fewer)
  followed by a capitalised line is treated as a heading.
- Only short English briefs were tested; long briefs and non-Latin text normalisation are untested.
- Jira import behaviour for Epic rows and blank Priority (see import notes); parent links are not
  in the CSV columns.

## How this was built

- The plan was drafted with AI help in a planning conversation (shared with Task 2):
  `chats/00_planning_chat_task2_and_task1.txt`.
  Short version: `PLAN.md`; full spec: `PLAN_full.md`.
- The code was built with Claude Code in a build chat, one stage per prompt (P1 plan review,
  P2-P6 one stage each, P7 review and edge cases, P8 README): `chats/01_build_chat.md`.
- A final review chat checked the tool against the handbook, fixed D30-D32, re-ran both demo
  briefs and re-verified the outputs: `chats/02_review_and_rerun_chat.md`.
- Real errors from each run were pasted back and fixed in code or prompts, never in output files
  (`defects_log.md`, `out/iterations/`).

## Deliverables index

| Item | Path |
|---|---|
| Planning chat (exported unedited by the student) | `chats/00_planning_chat_task2_and_task1.txt` |
| Build chat (exported unedited by the student) | `chats/01_build_chat.md` |
| Review and re-run chat (exported unedited by the student) | `chats/02_review_and_rerun_chat.md` |
| Plan (1 page) / full spec | `PLAN.md` / `PLAN_full.md` |
| Testing | `TESTING.md`, `defects_log.md` |
| README | `README.md` |
| Source | `main.py`, `llm.py`, `prompts.py`, `verify.py`, `tickets.py`, `export.py`, `conftest.py` |
| Tests | `tests/test_verify.py`, `tests/test_review_fixes.py`, `tests/test_tickets.py`, `tests/test_export.py`, `tests/edge/` |
| Demo briefs | `briefs/clear.txt`, `briefs/vague.txt` |
| Outputs | `out/clear/`, `out/vague/`, `out/edge_short/` (each `run.log`, `tickets.json`, `tickets_jira.csv`); `out/iterations/` |

Before submitting, check that no file contains the API key (must print `0`, covers `chats/` too):
```powershell
$k=[Environment]::GetEnvironmentVariable('GEMINI_API_KEY','User'); (Get-ChildItem -Recurse -File | Select-String -SimpleMatch -Pattern $k).Count
```
