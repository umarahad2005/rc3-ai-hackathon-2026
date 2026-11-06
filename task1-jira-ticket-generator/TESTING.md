# TESTING - Brief2Jira (Task 1)

Checks T1-T14 come from PLAN_full.md section 7. Each result below was verified against the
code or the saved outputs (`out/clear`, `out/vague`, `out/edge_short`) on 2026-11-05. Nothing is
marked PASS unless it was checked. "PARTIAL" means the check was run and part of the expected
result was not met.

Final outputs and the model that produced them (first line of each `run.log`):

| Output | Brief | Model |
|---|---|---|
| `out/clear/` | briefs/clear.txt | gemini-3-flash-preview, `GEMINI_THINKING_BUDGET=1024` (re-run 14:00, after D30/D31) |
| `out/vague/` | briefs/vague.txt | gemini-3-flash-preview, `GEMINI_THINKING_BUDGET=1024` (re-run 13:58, after D30) |
| `out/edge_short/` | tests/edge/short.txt ("Build an app.") | gemini-3-flash-preview (13:28 run) |

Why the clear/vague outputs were re-made: later runs that failed with 503 / 403 / MAX_TOKENS had
deleted the earlier good exports, leaving only failed run.logs (defect D30). Those failed logs
are kept in `out/iterations/` (`clear_iter10-11`, `vague_iter7-8`). A first re-run with
`gemini-flash-lite-latest` worked but was weaker: clear gave a member-identification task a
"High" priority that the brief gives only to booking and cancellation (D31,
`out/iterations/clear_iter12_priority_leak_run.log`), and vague copied whole brief sentences as
titles, made one epic per task and asked no payment question
(`out/iterations/vague_iter9_flash_lite_weak_titles_run.log`). The final outputs use
gemini-3-flash-preview, the same model as the earlier good runs.

All T3/T4/T5/T7/T9/T10 output checks below were re-run on the final files with a small
Python check (quote_ok on every AC/question quote, ID sequence, dangling dependencies, lost
questions, CSV header/BOM, parse_ac round-trip, Labels, Priority column, invention_lint).

## Results

Offline unit tests: `python -m pytest -q` -> **80 passed, 1 warning** (the warning is a pytest
deprecation inside the `anyio` plugin, not in this code). Files: tests/test_verify.py (40),
tests/test_review_fixes.py (20), tests/test_tickets.py (11), tests/test_export.py (9).

| # | Check | Expected | Result | Evidence |
|---|---|---|---|---|
| T1 | quote_ok (exact, curly quotes, whitespace, paraphrase, ellipsis, 1-word) and sentence_of | all pass | **PASS** | `test_exact_quote_passes`, `test_curly_quotes_pass`, `test_extra_whitespace_and_line_break_pass`, `test_paraphrase_fails`, `test_ellipsis_fails`, `test_one_word_quote_fails`, `test_sentence_of_finds_right_sentence` all pass |
| T2 | Contradiction with 1 quote / same quote twice / nested ("web only" vs "want web only") / one sentence | rejected | **PASS** | `test_contradiction_with_one_quote_rejected`, `test_contradiction_same_quote_twice_rejected`, `test_contradiction_nested_quote_rejected`, `test_contradiction_same_sentence_rejected` pass; `test_valid_contradiction_kept` shows a valid pair survives |
| T3 | Every AC and source printed next to its quote; 100% verified | 100% | **PASS** | Every AC line in the run.logs has the form `- <text>   <- "<quote>"`. Re-checked with `verify.quote_ok` over the saved tickets.json: clear 9/9 AC quotes, vague 6/6, edge_short 0 AC; all question quotes (clear 4 questions, vague 11, edge_short 7) found in the brief |
| T4 | Invented-detail hunt: denylist lint, content-word lint, search of tickets.json + tickets_jira.csv | 0 terms not in the brief | **PARTIAL** | Denylist `invention_lint` re-run on all three outputs: 0 warnings. Search for `stripe|paypal|refund|invoice|currency|waitlist|notification|login|password|dashboard|seconds|%`: vague 0 hits; clear and edge_short hit only `notification` inside the PLAN's templated integration question ("payments, accounts, notifications"), not in any ticket title, description or AC. Content-word lint is **not 0**: clear 1 (`management` in an epic title), vague 8 (`platform`, `integrate`, `visibility`, `weekly`, `administrators` in epic descriptions; `select`, `apply`, `receive` in titles), edge_short 1 (`requested`). Reviewed: these are paraphrase words, no invented feature, technology, number or rule |
| T5 | Priority / Estimate / Deadline match the brief or "Not specified"; CSV Priority blank when not stated | pass | **PASS** | clear: Priority High on TASK-005 (Book a class) and TASK-006 (Cancel a booking), Low on TASK-003 (printable list), Not specified on TASK-001/002/004; Deadline `15 March 2027` on all; Estimate Not specified. CSV Priority column `"", "", Low, "", High, High`. D31 guard: a priority now also needs its quote to name the task (`test_priority_must_name_the_task`). vague and edge_short: all three fields Not specified, CSV Priority blank on every row. Every row's `h3. Details` line repeats the same priority |
| T6 | The 8 vague.txt traps give questions of the right category | 8/8 | **PARTIAL - 8/8 raised, 6/8 exact category** | 1 contradiction Q-001 (quotes from S3 and S10) OK; 2 vague Q-002/Q-003/Q-004 for fast / modern / secure, no number suggested OK; 3 ORMS undefined_term Q-005 OK; 4 loyalty undefined_term Q-006 OK; 5 "pay online" raised as **missing** Q-010 (payment provider only), expected scope_gap with methods/currency/refunds; 6 delivery slots scope_gap Q-007 OK; 7 "usual reports" vague Q-008 OK; 8 priorities template Q-011 OK, but the deadline question is the LLM's **vague** Q-009 on "as soon as possible", not the missing-deadline template. No date or priority was invented; all fields Not specified |
| T7 | clear.txt: most tasks Ready, deadline 15 March 2027, 1 quoted dependency, no false platform question | pass | **PASS** | 3 of 4 tasks Ready (TASK-002, 003, 006); TASK-005 (Book a class) waits on Q-001 (confirmation channel). Deadline 15 March 2027. No platform, users, deadline or priority question. Questions: Q-001 confirmation channel, Q-002 staff identification (scope_gap), Q-003 membership-number validation (missing), Q-004 integrations template. One dependency, as the PLAN expects: TASK-005 Book a class -> TASK-002 Create classes ("Members can only book classes that staff have already created") |
| T8 | Status logic: questions make a ticket Needs clarification; epic inherits from children | pass | **PASS** | `test_status_logic_and_epic_inheritance`, `test_epic_with_general_question_needs_clarification` pass. Re-derived the status of every ticket in the three outputs from its open questions and children: 0 mismatches |
| T9 | Unique IDs, no dangling dependencies, no lost questions | pass | **PASS** | Tests `test_ids_sequential_unique_epic_then_tasks`, `test_dependencies_remapped_no_dangling`, `test_no_lost_questions` pass. Outputs: IDs sequential TASK-001.. (clear 6, vague 8, edge_short 2), same keys on every ticket, 0 dangling deps, every question (4 / 11 / 7) is on a ticket or in general_questions |
| T10 | CSV round-trip: DictReader + parse_ac recovers every task AC; epics return [] | pass | **PASS** | `test_csv_round_trip` passes. Re-run on the three real CSVs: header exactly `Summary,Issue Type,Description,Priority,Labels`, no BOM, parse_ac equals the ticket AC texts for every row, every epic has `h3. Acceptance Criteria` + `Not applicable (epic) ...` and returns [], Labels = ticket ID |
| T11 | Empty or whitespace-only brief | exit 1 before any API call | **PASS** | `python main.py tests/edge/empty.txt` -> `ERROR: brief is empty`, exit 1. `tests/edge/whitespace.txt` (spaces and newlines only) -> same, exit 1. With a dummy key set (`GEMINI_API_KEY=dummy-not-a-key`) the empty brief still exits 1, so it stops before the key check and before any API call (main.py loads the brief first) |
| T12 | "Build an app." | at most 1 epic, mostly questions, no invented features | **PASS** | out/edge_short: 1 epic + 1 story, 7 questions (users, platform, deadline, core features, integrations, priorities, AC), 0 AC (parse_ac -> [], so Track A would not merge), both tickets Needs clarification, 0 denylist warnings |
| T13 | Key unset | exit 2, clear message, no traceback | **PASS** | `cmd /c "set GEMINI_API_KEY=&& python main.py briefs\clear.txt --out %TEMP%\nokey2"` -> `ERROR: GEMINI_API_KEY not set`, exit 2, no traceback. Same with `env -u GEMINI_API_KEY python main.py briefs/clear.txt`; no output folder created |
| T14 | Manual: Ctrl+F 5 random quotes in the brief | all found | **PASS 5/5** | 5 quotes drawn at random (seed 14) from the 12 distinct quotes in out/vague/tickets.json and searched in briefs/vague.txt with Python: "Admins should get the usual reports every week", "so the warehouse sees them straight away", "Delivery slots are important to us" found as-is; "loyalty scheme to work like last time" and "Customers will download our new app from the App Store and Google Play" found once the brief's hard line wraps are joined (they cross a line break, so a plain editor Ctrl+F would miss them) |

**Summary: 12 PASS (T1-T3, T5, T7-T14), 2 PARTIAL (T4 content-word lint not 0; T6 6/8 exact categories), 0 FAIL.**

Real failure paths seen during the build (from `out/iterations/`): Stage 2 `output truncated
(finish_reason=FinishReason.MAX_TOKENS, max_output_tokens=8192)` with gemini-3-flash-preview
(clear_iter8), daily 429 quota failing at once (clear_iter6), and a 503 retried once then exit 3
(clear_iter7, vague_iter4). Each ended with `No export written.` and exit 3.

## Defects found and fixed

Full table with root causes: `defects_log.md`. Run logs for each iteration: `out/iterations/`.
All fixes were in code or prompts; output files were never hand-edited.

| # | Time | Error / bad output | Fix |
|---|---|---|---|
| D1 | 12:46 | Hard-wrapped briefs split mid-sentence, so a valid contradiction would be rejected as "same sentence" | `verify.unwrap()` re-joins wrapped lines before splitting |
| D2 | 12:48 | clear.txt gave 20 tickets / 5 epics, one per rule | Prompts: one task per capability; rules become AC |
| D3 | 12:48 | Most tasks cited the user-group sentence as source | tickets.py ranks feature/constraint facts first |
| D4 | 12:48 | `unsourced word 'launches'` though brief says "launch" | Lint also strips `es` |
| D5 | 12:50 | vague AC "The platform is web-only" picked a side of the contradiction | Code drops AC quoting either contradiction side |
| D6 | 12:50 | `Priority: as soon as possible` | Priority kept only if its quote has a priority word |
| D7 | 12:50 | Questions suggested answers "(e.g., CSV, PDF, in-app dashboard)" | `strip_examples()` + prompt rule |
| D8 | 12:50 | No vague question for "fast" | Prompt: one question per quality word |
| D9 | 12:55 | Invented task "Authenticate front-desk staff" | Reject meta-only tasks with no verified AC |
| D10 | 12:58 | D9 guard rejected the real reports task | Guard narrowed |
| D11 | 12:58 | Epic title "Customer Online Ordering (Web)" leaked a side | Avoid-words passed to Stage 4 + side lint |
| D12 | 12:58 | Priority question on clear.txt though priorities are stated | Reject LLM `missing` question on a covered topic |
| D13 | 12:59 | 429 twice -> exit 3, stale exports left beside the failed run.log | API message in error; old exports deleted at start |
| D14 | 13:01 | Real gap rejected because `web` matched "web application" | Narrow topic patterns |
| D15 | 13:02 | `503 UNAVAILABLE` -> exit 3 with no retry | 503 treated as transient (wait 30 s, retry once) |
| D16 | 13:08 | "Build an app." got no platform question (bare "app" counted as a platform) | `PLATFORM_RE` matches whole platform words only |
| D17 | 13:10 | `429 RESOURCE_EXHAUSTED` daily free-tier quota | No code change; clean exit 3 |
| D18 | 13:15 | Values not supported by their quote kept (`Highest` from "low priority") | `_value_problem()` checks value inside quote |
| D19 | 13:16 | `TypeError: unhashable type: 'list'` crash, no run.log | `_str_list()`; any exception -> exit 3 with run.log |
| D20 | 13:17 | Retry notice missing from run.log | `call_json(log=)` tees it; daily quota fails at once |
| D21 | 13:18 | Questions linked to the wrong tasks (1 of 7 Ready on clear) | Stricter link rules |
| D22 | 13:19 | Feature "important" question suppressed the priority template | `field_question()` |
| D23 | 13:20 | Dependency on an epic kept | Only task targets allowed |
| D24 | 13:21 | Invented wording ("notifications", ORMS expanded) in descriptions | Prompt + `sanitize_descriptions()` + title/description lint |
| D25 | 13:22 | `Admins` rejected as "quote not in brief" (too short) | New reason "quote too short"; prompt asks for the clause |
| D26 | 13:23 | "usual reports" classed undefined_term; duplicate loyalty question | GAPS prompt rules |
| D27 | 13:24 | Ungrouped Stage 3 print, lost `Sn:` prefix, usage error exit 2, etc. | Several small fixes (see log) |
| D28 | 13:25 | Daily quota, 503s, and Stage 2 MAX_TOKENS on gemini-3-flash-preview | Used `GEMINI_THINKING_BUDGET=1024` and `--model` |
| D29 | 13:40 | Two deadline questions on vague | Deadline topic pattern also matches launch / target date |
| D30 | 13:50 | Failed re-runs (503, 403, MAX_TOKENS) deleted the last good tickets.json / CSV, so out/clear and out/vague had no export | Failed run writes `failed_run.log` and leaves run.log + exports untouched; exports written via temp files. Test `test_failed_run_keeps_previous_good_exports` |
| D31 | 13:57 | clear: "Identify as a member" got Priority High from "Booking and cancellation are high priority." | `priority_names_task()`: the priority quote must share a content word with the task. Test `test_priority_must_name_the_task` |

Known remaining issues (from defects_log.md, still true in the final outputs): no "freed place /
waiting list" question on clear.txt; vague asks for the payment *provider* but not for payment
methods / currencies; the content-word lint and the D31 priority check use simple 4-letter
word stems, so a priority sentence that names a feature with a different word (a synonym) would
be dropped to "Not specified" + question (safe direction, but a false negative); vague payment question is `missing` instead of `scope_gap`;
the platform contradiction Q-001 is linked only to TASK-002; content-word lint gives harmless
paraphrase warnings.

## Not tested

- **Broken-JSON retry** (`call_json` retry with the parse error, then `failed_<stage>.txt`): never
  happened in a real run and there is no unit test for it.
- **MAX_TOKENS truncation**: not unit-tested, but it happened for real once (D28,
  `out/iterations/clear_iter8_gemini3_max_tokens_run.log`) and exited 3 with no export.
- **Non-English briefs** and normalisation of non-Latin text.
- **Real Jira import** of `tickets_jira.csv` (no Jira instance was used); only the CSV round-trip
  through `csv.DictReader` + `parse_ac` was tested.
- Long briefs (only the ~150-170 word demo briefs and the one-line edge case were run).
