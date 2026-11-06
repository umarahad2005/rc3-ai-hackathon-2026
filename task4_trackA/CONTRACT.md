# Track A - Automated PR Reviewer: module contract

Python 3.12. Libraries: `requests`, `google-genai`, `pytest`, plus the standard library only (`http.server` for the webhook).
All secrets come from environment variables only: `GITHUB_TOKEN`, `GEMINI_API_KEY`, `GEMINI_MODEL` (default `gemini-2.5-flash`), `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, `TICKETS_CSV` (fallback ticket source), `WEBHOOK_SECRET`, and `MAX_DIFF_CHARS` (default 60000). Never print a secret.

Flow: webhook -> extract ticket ID -> fetch ticket + AC -> fetch diff -> LLM verdict -> action.
**Safety rule:** the only path that merges is `fulfilled is True` (a real bool) with a valid ticket, non-empty AC and a diff within the size limit. Every other case blocks: commit status `failure` plus a PR comment that says what went wrong.

## config.py
- `get(name, default=None)`
- `MAX_DIFF_CHARS`, `STATUS_CONTEXT = "ai-pr-reviewer"`

## story_fetcher.py
- `class TicketError(Exception)`
- `TICKET_RE = r"([A-Z][A-Z0-9]+-\d+)"`
- `extract_ticket_id(branch, title) -> str | None`: try the branch first, then the title.
- `parse_ac(desc) -> list[str]`: exact copy of Task 1 `export.parse_ac`:
  ```
  re.search(r"h3\.\s*Acceptance Criteria\s*\n(.*?)(?=\nh3\.|\Z)", desc, re.S); keep lines starting "* "
  ```
- `fetch_ticket(ticket_id) -> {"id","title","description","acceptance_criteria":[str],"source":"jira"|"csv"}`
  - If `JIRA_BASE_URL`, `JIRA_EMAIL` and `JIRA_API_TOKEN` are all set: Jira REST API v2 `GET {base}/rest/api/2/issue/{id}?fields=summary,description,labels`, basic auth, timeout 15.
  - Else if `TICKETS_CSV` is set: read the Task 1 `tickets_jira.csv` (columns `Summary,Issue Type,Description,Priority,Labels`) and pick the row whose `Labels` equals the ID (for example `TASK-004`).
  - Raises `TicketError` when there is no source configured, the ticket is not found, or there is an HTTP error.
  - An empty AC list is returned as `[]`. The pipeline handles it.

## code_fetcher.py
- `class GitHubError(Exception)`
- `API = "https://api.github.com"`
- `gh(method, path, **kw) -> requests.Response`: uses the Bearer `GITHUB_TOKEN` header. Raises `GitHubError` on 4xx/5xx, with the status and message.
- `fetch_pr(repo, number) -> {"number","title","head_ref","head_sha","base_ref","state","merged"}`
- `fetch_diff(repo, number) -> str`: `GET /repos/{repo}/pulls/{n}` with `Accept: application/vnd.github.diff`.

## evaluator.py
- `SYSTEM_PROMPT`: the handbook blueprint verbatim, plus "Return ONLY the JSON object."
  > You are an expert Senior Code Reviewer. Compare the provided Code Diff against the provided Jira/Azure Acceptance Criteria. Answer in JSON with two keys: fulfilled (true/false) and feedback (markdown string). If fulfilled is false, provide a precise list of missing requirements or code bugs. If true, provide a brief summary of the successful verification.
- `check_diff(diff, max_chars) -> str | None`: returns an error message for an empty or whitespace-only diff, or for a diff over `max_chars`.
- `build_user_message(ticket, diff) -> str`: ticket ID, title, numbered AC, then the diff in a fenced block.
- `parse_verdict(text) -> (verdict | None, error | None)`
  - Strip code fences, run `json.loads`, and require a dict.
  - `fulfilled` must be a real bool (not the string "true" and not missing).
  - `feedback` must be a str.
  - Otherwise return the error "LLM answer is not valid JSON" or "fulfilled key missing or not boolean".
- `evaluate(ticket, diff, call=None) -> {"fulfilled": bool | None, "feedback": str, "error": str | None, "raw": str}`
  - `call(system, user) -> str` is injectable for tests. The default calls Gemini through google-genai with `temperature=0`, `response_mime_type` application/json and `max_output_tokens` 4096.
  - API errors become `error`. It never raises.

## executor.py
- `act(repo, pr, verdict, dry_run) -> list[str]` (human-readable log of the actions)
  - `verdict` = `{"fulfilled": bool | None, "feedback": str, "error": str | None, "reason": str}`
  - **Merge path** (`verdict["fulfilled"] is True` and not `error`):
    1. POST `/repos/{repo}/statuses/{head_sha}` with state `success` and context `ai-pr-reviewer`.
    2. POST an issue comment with "AI review: PASSED" and the feedback.
    3. PUT `/repos/{repo}/pulls/{n}/merge` with `merge_method` `squash`.
  - **Block path** (everything else):
    1. POST the status with state `failure` and a description of 140 chars or fewer.
    2. POST an issue comment `/repos/{repo}/issues/{n}/comments`. The body starts `## AI review: FAILED - merge blocked` and is followed by the reason and the feedback.
  - `dry_run=True` performs nothing and returns lines prefixed `[DRY-RUN]`.

## pipeline.py
- `review_pr(repo, number, dry_run=False, call=None) -> dict` with keys `ticket_id`, `decision` ("MERGE" | "BLOCK"), `reason`, `actions`, `verdict`.
- Steps:
  1. `fetch_pr`
  2. `extract_ticket_id`
  3. `fetch_ticket`
  4. if AC is empty, block
  5. `fetch_diff`
  6. `check_diff`
  7. `evaluate`
  8. `act`
- Any failure at any step blocks with a clear reason. If even `fetch_pr` fails, report the error and do not call `act`.
- Prints each stage as it runs.

## server.py
- stdlib `ThreadingHTTPServer`, `POST /webhook`
- If `WEBHOOK_SECRET` is set, verify `X-Hub-Signature-256` with HMAC; on a mismatch return 401.
- Header `X-GitHub-Event` `pull_request` with action `opened`, `synchronize`, `reopened` or `ready_for_review`: read `repository.full_name`, `number`, `pull_request.title` and `head.ref`, run `review_pr`, and return 200 with the result as JSON.
- Other events return 200 `{"ignored": ...}`. Bad JSON returns 400.
- `GET /health` returns 200.

## cli.py
- `python cli.py review --repo owner/name --pr N [--dry-run]`
- `python cli.py serve [--port 8000] [--dry-run]`
- `python cli.py replay payload.json [--url http://localhost:8000/webhook]`: POSTs a saved GitHub webhook payload, signed if `WEBHOOK_SECRET` is set.

## tests/
Offline pytest only, with no network: mock `requests` / inject `call`. Cover:
- no ticket ID → BLOCK
- ticket not found → BLOCK
- empty AC → BLOCK
- invalid JSON → BLOCK
- `fulfilled` missing or `"true"` as a string → BLOCK
- empty diff → BLOCK
- oversized diff → BLOCK
- `fulfilled` true → MERGE path calls merge
- `parse_ac` on a Task 1 CSV description
- webhook signature check
