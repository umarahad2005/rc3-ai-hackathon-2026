# Task 4 Submission: **Track B: GitHub Repository Analyzer CLI**

RC3 AI Hackathon, 2026-11-05. Individual work.

## Deliverables (as listed in the handbook)

| # | Deliverable | Where |
|---|---|---|
| 1 | Exported chat(s): complete and unedited | `../chats/task4b_chat_export.txt` (Claude Code `/export` of the Task 4 conversation) |
| 2 | Working tool: source code + README (track, libraries, how to run) | `analyze.py`, `analyzer/`, `README.md`, `requirements.txt` |
| 3 | Demo evidence: full report for 2 or more public repositories | `demo/expressjs_express.txt`, `demo/psf_requests.txt`, `demo/hello_world.txt`, `demo/unmapped_mit_hackathon.txt` |
| + | Failure handling evidence | `demo/failures.txt` (live: exit 2, 3, 5), `demo/rate_limit_simulated.txt` (mocked: exit 4), `demo/tests_offline.txt` (10 offline tests, all pass) |
| + | Planning documents written before the code | `PLAN.md`, `plan/SPEC.md`, `plan/STAGE_PROMPTS.md` |

## How to run

```powershell
cd task4
pip install -r requirements.txt          # requests, rich
python analyze.py https://github.com/expressjs/express
python analyze.py help                   # usage guide
python -m unittest -v tests.test_offline # offline tests
```
Optional: create a `.env` file and set `GITHUB_TOKEN` (5,000 requests/hour instead of 60).
The token is read only from the environment or `.env`. It is never written in the code or in the submitted files.

## How the work was done (summary of the chat)

1. **Planned:** requirements, a module layout, the GitHub endpoints for each section, input/output contracts for every
   stage, and a build/test order (`PLAN.md`, `plan/`). A reviewer pass found 29 inconsistencies between the spec and the
   stage prompts, and all were fixed before any code was written.
2. **Built in stages:** client and errors, then fetch and tech stack, structure, complexity, dependencies, activity, and
   the report. One independent agent tested the integration and another audited the code.
3. **Tested and reviewed:** live runs on 4 repositories plus the failure cases. The audit fixed a possible token leak to
   non-GitHub hosts and an invented "0.0% up to date" figure.
4. **Fixed from my own test:** running my own repository showed 3 problems, all fixed and re-tested: a contradictory activity
   message, manifests in sub-folders being missed, and missing folder-purpose notes.

## Known limitations
See `README.md` > "Known limitations". In short: the complexity score is a structural heuristic (not lines of code), only
`requirements.txt` / `package.json` are parsed, and version ranges are not judged.

## Security note
A GitHub token was pasted into the AI chat once by mistake while setting up `.env`. The chat export is left unedited, as
the rules require, so it was in the export; in this public repo it is replaced with `[REDACTED]`. That token was revoked on GitHub at **__:__** and
replaced, so it no longer works. No token appears in the code, the README or the demo files, and `.env`
is not included in this submission.
