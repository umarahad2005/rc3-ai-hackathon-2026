# 📘 Setup and Run Guide

Every command below is for **PowerShell on Windows**. On macOS or Linux, use `/` in paths and `export NAME=value` instead of `$env:NAME = "value"`.

**Contents**
- [0. One-time setup](#0-one-time-setup)
- [🔐 Secrets](#-secrets)
- [1. Task 1: Jira Ticket Generator](#1-task-1-jira-ticket-generator)
- [2. Task 2: Near-Duplicate Detection](#2-task-2-near-duplicate-detection)
- [4A. Task 4 Track A: AI PR Reviewer](#4a-task-4-track-a-ai-pr-reviewer)
- [4B. Task 4 Track B: GitHub Repo Analyzer](#4b-task-4-track-b-github-repo-analyzer)
- [Troubleshooting](#troubleshooting)

---

## 0. One-time setup

| Tool | Needed for | Check |
|---|---|---|
| Python 3.10+ (3.12 tested) | everything | `python --version` |
| Git | everything | `git --version` |
| GitHub CLI (`gh`) | Task 4A | `gh auth status` (log in with `gh auth login`) |
| Gemini API key (free) | Tasks 1 and 4A | from https://aistudio.google.com → **Get API key** |

```powershell
git clone https://github.com/umarahad2005/rc3-ai-hackathon-2026.git
cd rc3-ai-hackathon-2026
$REPO = (Get-Location).Path        # the per-task RUN.md files use $REPO
```

---

## 🔐 Secrets

This repo contains **no** `.env` or `.env.example` files. Create a `.env` yourself inside the task folder that needs one. It is git-ignored, so it never gets committed.

```powershell
notepad .env     # inside the task folder; Notepad asks to create the file
```

| Variable | Task | Required? | Purpose |
|---|---|---|---|
| `GEMINI_API_KEY` | 1, 4A | ✅ | The LLM calls |
| `GEMINI_MODEL` | 1, 4A | optional | For example `gemini-flash-lite-latest` (the free tier has a higher quota) |
| `GITHUB_TOKEN` | 4A, 4B | 4A: optional (`start.py` uses `gh auth token`); 4B: optional | GitHub API access. 4B goes from 60 to 5,000 requests/hour |
| `JIRA_TICKETS_DIR` | 4A | optional | Folder of Jira JSON tickets (default `tickets/jira`) |
| `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN` | 4A | optional | Read tickets from live Jira instead of local files |
| `WEBHOOK_SECRET` | 4A | optional | Checks `X-Hub-Signature-256` in webhook mode |
| `MAX_DIFF_CHARS` | 4A | optional | Larger diffs are blocked, never cut (default 60000) |

A real environment variable (`$env:NAME` or `setx`) always overrides `.env`. **Never paste keys into code, chats or commits.**

---

## 1. Task 1: Jira Ticket Generator

📁 `task1-jira-ticket-generator/` · detailed docs: [README](task1-jira-ticket-generator/README.md) · [RUN](task1-jira-ticket-generator/RUN.md) · [TESTING](task1-jira-ticket-generator/TESTING.md)

```powershell
cd $REPO\task1-jira-ticket-generator
pip install -r requirements.txt
notepad .env                                        # GEMINI_API_KEY=...  GEMINI_MODEL=gemini-flash-lite-latest
python -m pytest -q                                 # 80 offline tests, no API calls

python main.py briefs\clear.txt --out out\clear     # well-specified brief
python main.py briefs\vague.txt --out out\vague     # vague brief full of traps
python main.py path\to\your_brief.txt --out out\mine
```

**Output** (in the `--out` folder): `run.log` (the full report), `tickets.json`, and `tickets_jira.csv`, which you can import into Jira via *Settings → System → External system import → CSV*.

**Exit codes:** `0` success · `1` empty brief · `2` no API key · `3` an LLM stage failed (see `failed_run.log`; wait a minute and re-run).

---

## 2. Task 2: Near-Duplicate Detection

📁 `task2-near-duplicate-detection/`

| File | Purpose |
|---|---|
| `Task2_NearDuplicates_final.ipynb` | The full solution: method, correctness check, parameter justification, complexity analysis, timed full run |
| `lsh_core.py` | Core algorithm: 5-word shingles → 64-bit hashes → MinHash (k=100) → LSH banding (b=20, r=5) → exact Jaccard check |
| `dev_test.py`, `full_test.py` | Local test runs on the dev set and the full set |

**Run on Google Colab (recommended):**
1. Open https://colab.research.google.com → **Upload** → `Task2_NearDuplicates_final.ipynb`.
2. Upload the organiser's `docs.csv`, `dev_docs.csv` and `dev_ground_truth.csv` (not in this repo).
3. **Runtime → Run all.** The last cell times the full run and writes `submission.csv`.

**Run locally:** put the organiser data in `lsh_task/` at the repo root (it is git-ignored), then:
```powershell
cd $REPO\task2-near-duplicate-detection
pip install -r requirements.txt
python dev_test.py      # precision and recall on the dev set for several (b, r)
python full_test.py     # full corpus timing
```

---

## 4A. Task 4 Track A: AI PR Reviewer

📁 `task4a-ai-pr-reviewer/` · detailed docs: [README](task4a-ai-pr-reviewer/README.md) · [RUN (every command)](task4a-ai-pr-reviewer/RUN.md) · [CONTRACT](task4a-ai-pr-reviewer/CONTRACT.md)

### How it works
A push to a branch whose name contains a **ticket key** (for example `feature/RC3-20-login`) goes through these steps:
1. A PR is opened automatically.
2. The ticket is loaded from Jira, a local Jira JSON file, or the Task 1 CSV, and its **Acceptance Criteria** are parsed.
3. The diff is fetched.
4. Gemini returns `{fulfilled, feedback}`.
5. ✅ **MERGE** (status Success, comment, squash-merge) or ❌ **BLOCK** (status Failed, comment listing what is missing).

It is safe by default. It **blocks** when: there is no ticket key, the ticket is not found, the ticket has no acceptance criteria, the diff is empty or too large, the LLM answer is invalid, or the API fails.

### Step 1: install and test
```powershell
cd $REPO\task4a-ai-pr-reviewer
pip install -r requirements.txt
pip install pypdf                    # only needed for .pdf tickets
gh auth login                        # once
notepad .env                         # GEMINI_API_KEY=...  GEMINI_MODEL=gemini-flash-lite-latest
python -m pytest -q                  # 64 offline tests
```

### Step 2: add a ticket
Put a ticket in `tickets\inbox\`. It can be `.txt`, `.md`, `.docx`, `.pdf`, `.json` or `.csv`. It needs a key and an **Acceptance Criteria** heading:
```text
Key: RC3-20
Summary: Show class full message

Acceptance Criteria:
- When a class reaches its capacity, members see the message "Class full".
- A member cannot book a class that is full.
```
`start.py` imports it automatically. To import by hand, run `python cli.py import-tickets`. A ticket without acceptance criteria is **never** merged.

### Step 3: start the reviewer (one command)
```powershell
python start.py --repo <owner>/<repo>            # LIVE: comment + status + merge
python start.py --repo <owner>/<repo> --dry-run  # decides only, changes nothing on GitHub
```
`start.py` finds a working GitHub token (from `.env` or `gh auth token`), checks the Gemini key, imports the tickets, then **watches** the repo every 10 seconds. Leave it running; **Ctrl+C** stops it.

### Step 4: push code
In a second window, inside a clone of the target repo:
```powershell
git checkout main; git pull
git checkout -b feature/RC3-20-class-full        # the branch name MUST contain the ticket key
# ... add or edit code ...
git add -A; git commit -m "RC3-20 class full message"; git push -u origin HEAD
```
Within a few seconds, the `start.py` window prints the 6 stages and the decision. On GitHub, the PR gets the `ai-pr-reviewer` status, an "AI review" comment, and is merged if the code passes.

### Other modes
```powershell
python cli.py review --repo <owner>/<repo> --pr 5 [--dry-run]   # review one existing PR
python cli.py serve --port 8000                                  # GitHub webhook listener (expose it with ngrok)
python cli.py watch --repo <owner>/<repo> --interval 10          # what start.py runs, without the setup steps
```
Use **one** of `start.py`/`watch` **or** `serve`, never both at once. If you do, each push is reviewed twice.

---

## 4B. Task 4 Track B: GitHub Repo Analyzer

📁 `task4b-github-repo-analyzer/` · detailed docs: [README](task4b-github-repo-analyzer/README.md)

```powershell
cd $REPO\task4b-github-repo-analyzer
pip install -r requirements.txt                       # requests + rich only
python analyze.py https://github.com/psf/requests
python analyze.py github.com/expressjs/express.git/   # many URL forms are accepted
python analyze.py https://github.com/octocat/Hello-World --save demo\hello_world.txt
python analyze.py help                                # usage, token status, exit codes
python -m unittest -v tests.test_offline              # offline tests
```

**The report has five sections:** 1) Tech stack with evidence · 2) File structure · 3) Complexity score (0–100, formula printed) · 4) Dependency health (latest versions from PyPI and npm) · 5) Commits-per-week chart and top contributors.

It never invents data. Anything it cannot determine is printed as `Not available: <reason>`. An invalid URL, a missing repo, rate limits and missing manifests all give a clear message.

**Optional:** put `GITHUB_TOKEN=<token>` in `.env` to get 5,000 requests/hour instead of 60. A fine-grained token with *public repositories, read-only* access is enough.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `429` / `RESOURCE_EXHAUSTED` from Gemini | Free-tier quota used up. Wait a minute, or set `GEMINI_MODEL=gemini-flash-lite-latest` |
| `503` from Gemini | The model is overloaded. Re-run, or pick another model |
| 4A: `GitHub ... 404` | The token can't see the repo. Run `gh auth login`, or remove the old `GITHUB_TOKEN` from `.env` |
| 4A: PR blocked with "No ticket ID" | The branch name or PR title must contain the key, for example `feature/RC3-20-...` |
| 4A: PR never merges | Check that the ticket has an `Acceptance Criteria:` heading with bullet points |
| 4B: rate limit message | Add `GITHUB_TOKEN` to `.env` (60 → 5,000 requests/hour) |
| Garbled bars when saving 4B output | Run `$env:PYTHONUTF8 = "1"` first |
