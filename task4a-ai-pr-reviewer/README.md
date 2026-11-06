# Task 4 - Track A: Automated PR Reviewer (Universal Webhook Listener)

**Chosen track: A.**

A pull request event comes in. The tool finds the ticket, reads the diff, and asks an LLM whether the diff meets the ticket's acceptance criteria. It then either **blocks** the PR or **merges** it:
- **Block:** sets the commit status `ai-pr-reviewer` to Failed and posts a comment.
- **Merge:** sets the status to Success, posts a comment and squash-merges the PR.

```
GitHub webhook --> server.py (HMAC check) --> pipeline.review_pr
   [1/6 webhook] code_fetcher.fetch_pr        PR title, branch, head SHA
   [2/6 story]   story_fetcher                ticket ID regex [A-Z][A-Z0-9]+-\d+ (branch, then title)
                                              -> Jira REST v2 issue  OR  Task 1 tickets_jira.csv (by Labels)
                                              -> parse_ac(): "h3. Acceptance Criteria" + "* " bullets
   [3/6 code]    code_fetcher.fetch_diff      GitHub API, Accept: application/vnd.github.diff
   [4/6 llm]     evaluator                    handbook prompt blueprint -> strict JSON {fulfilled, feedback}
   [5/6 decision] MERGE only if fulfilled is the boolean true, otherwise BLOCK
   [6/6 action]  executor                     status failure + comment | status success + comment + merge
```

## Safety: when the tool never merges
Each case below blocks the PR (Failed status plus a comment explaining why). Each one has an offline test in `tests/`:

| Situation | Result |
|---|---|
| No ticket ID in the branch or title | BLOCK, "No ticket ID ... found" (live demo: PR #3) |
| Ticket not found, fetch error, or no ticket source configured | BLOCK |
| Ticket has no acceptance criteria (for example a Task 1 epic, "Not applicable (epic)") | BLOCK |
| Diff empty, or larger than `MAX_DIFF_CHARS` (default 60000); it is never silently cut | BLOCK |
| LLM answer is not JSON, `fulfilled` is missing or not a real boolean (`"true"` or `1`), or the API fails | BLOCK |
| `fulfilled: false` | BLOCK with the LLM's list of missing requirements |
| The merge API call itself fails | reported as BLOCK |

The merge call sends `sha=<reviewed head SHA>`, so it can only merge the exact commit that was reviewed. `--dry-run` prints the actions and performs none.

## Libraries
Python 3.12, `requests`, `google-genai` (Gemini), and `pytest`. The webhook server uses the standard library's `http.server`.

## Setup
Set these as environment variables. Never put them in code or in the chat.

| Variable | Purpose |
|---|---|
| `GITHUB_TOKEN` | Needs repo access to the test repo. For example, `$env:GITHUB_TOKEN = (gh auth token)` |
| `GEMINI_API_KEY` | Free key from Google AI Studio. Set it with `setx` in your own terminal |
| `GEMINI_MODEL` | Optional. The default is `gemini-2.5-flash`. The demo used `gemini-flash-lite-latest` because the free daily quota for 2.5-flash was used up |
| `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN` | Optional. Pulls the ticket from the Jira REST API v2 |
| `JIRA_TICKETS_DIR` | Local Jira tickets: a folder of `<KEY>.json` files in exactly the shape `GET /rest/api/2/issue/<KEY>` returns, or a Jira search export `{"issues": [...]}`. Uses the same parser as live Jira, and also reads v3 ADF descriptions |
| `TICKETS_CSV` | Last-resort fallback: the Task 1 `tickets_jira.csv`, matched on the `TASK-00x` label |

### Ticket sources (first one configured wins)
1. **Live Jira:** set `JIRA_BASE_URL`, `JIRA_EMAIL` and `JIRA_API_TOKEN`. The tool calls REST v2 `/rest/api/2/issue/<KEY>`.
2. **Local Jira files:** set `JIRA_TICKETS_DIR`. Save a ticket from Jira, for example by opening `https://<site>/rest/api/2/issue/RC3-5` in the browser and saving the page as `RC3-5.json`. Or build the files from Task 1 with `python csv_to_jira_json.py tickets/clear_tickets_jira.csv tickets/jira`.
3. **Task 1 CSV:** set `TICKETS_CSV`.

The ticket description must contain `h3. Acceptance Criteria` followed by `* ` bullets. A ticket without acceptance criteria is never merged.
| `WEBHOOK_SECRET` | Optional. Enables the `X-Hub-Signature-256` check |
| `MAX_DIFF_CHARS` | Optional. Default 60000 |

## Run
```
pip install -r requirements.txt
python cli.py review --repo owner/name --pr 1 [--dry-run]     # review one PR now
python cli.py serve --port 8000 [--dry-run]                   # webhook listener: POST /webhook, GET /health
python cli.py replay demo/payload_pr1_opened.json --url http://localhost:8000/webhook
python -m pytest -q                                           # 64 offline tests
```
To receive real GitHub webhooks, expose the port with a tunnel (for example ngrok). Then add a webhook for "Pull requests" events with the same secret.

## Demo evidence
Test repository only: private repo `umarahad2005/rc3-pr-reviewer-demo`. The ticket is TASK-004 from Task 1, with this acceptance criterion: *When a class reaches its capacity, booking closes and members see the message "Class full".*

| File | What it shows |
|---|---|
| `demo/run_pr1_failed_via_webhook.txt`, `demo/server_log_pr1.txt` | PR #1 adds booking with no capacity check. It was sent through the webhook listener. The LLM returned `fulfilled=false` and listed the missing checks. Status **Failed**, comment posted, **not merged** |
| `demo/run_pr2_merged.txt` | PR #2 implements the capacity check and the "Class full" message. Result `fulfilled=true`, status Success, **squash-merged** |
| `demo/run_pr3_no_ticket_blocked.txt` | PR #3 has no ticket ID. It was blocked before any LLM call |
| `demo/github_state_pr1.json`, `demo/github_state_pr2.json` | GitHub's own record: PR #1 is OPEN with `ai-pr-reviewer` FAILURE; PR #2 is MERGED with SUCCESS |
| `demo/run_pr1_local_jira_dryrun.txt` | Same PR #1, with the ticket read from the local Jira file `tickets/jira/TASK-004.json` (`source=jira-local`). Dry-run, so it prints the BLOCK actions without performing them |
| `demo/tests_offline.txt` | pytest: 58 passed, including local Jira v2 files, a search export, a v3 ADF description, and missing or bad files |

## Known limits
- Feedback goes in one main PR comment, not inline comments on specific lines. The handbook allows either.
- The Failed status blocks merging only when branch protection requires the `ai-pr-reviewer` check.
- Azure DevOps is not implemented; the connectors support GitHub and Jira only.
- The LLM verdict is advisory, so a human should keep branch protection on.

## How this was built
Built with Claude Code in this session's chat (exported unedited as the Task 4 chat). The steps were:
1. A module contract (`CONTRACT.md`).
2. Three focused build stages: the fetchers, the evaluator, and the executor, pipeline and server. Each stage came with offline tests.
3. Live runs on the test repo.
