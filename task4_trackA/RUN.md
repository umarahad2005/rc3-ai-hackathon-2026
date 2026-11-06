# RUN.md: Task 4 Track A, Automated PR Reviewer (every command)

**What it does:** a ticket (in any format) becomes Jira JSON. A developer pushes code, and the tool opens a PR automatically. It then reads the ticket and the diff and asks the LLM whether the acceptance criteria are met.
- **Fulfilled:** status `ai-pr-reviewer` = Success, a PASSED comment, and an **automatic merge**.
- **Not fulfilled, or anything goes wrong:** status = **Failed**, a comment saying what is missing, and **no merge**.

All commands are for **PowerShell** on Windows. The examples use the test repo `umarahad2005/rc3-pr-reviewer-demo`.

---

## ⚡ QUICK START: copy and paste, block by block
Each block is complete. Paste it into the window named in its title. Sections 0–15 below explain every command in detail.

### Block 1: first time only (any window)
```powershell
cd C:\Users\umara\Downloads\RC3_AI_HACK\task4_trackA
pip install -r requirements.txt
pip install pypdf
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
```
In Notepad, set `GEMINI_API_KEY=...`, `GEMINI_MODEL=gemini-flash-lite-latest`, `JIRA_TICKETS_DIR=tickets/jira` and `WEBHOOK_SECRET=...`, then save. To make a secret:
```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

### Block 2: check everything works (Window A)
```powershell
cd C:\Users\umara\Downloads\RC3_AI_HACK\task4_trackA
$env:GITHUB_TOKEN = (gh auth token)
python -m pytest -q
python cli.py import-tickets
python cli.py review --repo umarahad2005/rc3-pr-reviewer-demo --pr 5 --dry-run
```
Expect: `64 passed`, the tickets imported, and a `decision=` line.

### Block 3: start the reviewer server (Window A); it stops any old server first
```powershell
cd C:\Users\umara\Downloads\RC3_AI_HACK\task4_trackA
Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
$env:GITHUB_TOKEN = (gh auth token)
python cli.py serve --port 8000
```
Leave it running.

### Block 4: start the public tunnel (Window B)
```powershell
ngrok http 8000
```
Leave it running. The GitHub webhook Payload URL must be **exactly** `<Forwarding URL>/webhook` (section 8.4).

### Block 5: check the tunnel and the webhook (Window C)
```powershell
Invoke-RestMethod http://localhost:8000/health
(Invoke-RestMethod http://127.0.0.1:4040/api/tunnels).tunnels.public_url
$h = gh api repos/umarahad2005/rc3-pr-reviewer-demo/hooks --jq '.[0].id'
gh api repos/umarahad2005/rc3-pr-reviewer-demo/hooks/$h --jq '.config.url'
gh api "repos/umarahad2005/rc3-pr-reviewer-demo/hooks/$h/deliveries?per_page=5" --jq '.[] | "\(.delivered_at) \(.event)/\(.action) \(.status_code)"'
```
Expect: `ok: True`; the hook URL equals the tunnel URL plus `/webhook`; the deliveries show 200.

### Block 6: get a working copy of the demo repo (Window C, once)
```powershell
cd $env:TEMP
if (-not (Test-Path demo-live)) { gh repo clone umarahad2005/rc3-pr-reviewer-demo demo-live }
cd $env:TEMP\demo-live
git checkout main; git pull
```

### Block 7: add a new ticket (Window C)
```powershell
@"
Key: RC3-10
Summary: Show class full message

Acceptance Criteria:
- When a class reaches its capacity, members see the message "Class full".
- A member cannot book a class that is full.
"@ | Set-Content C:\Users\umara\Downloads\RC3_AI_HACK\task4_trackA\tickets\inbox\RC3-10.txt -Encoding utf8
Push-Location C:\Users\umara\Downloads\RC3_AI_HACK\task4_trackA; python cli.py import-tickets; Pop-Location
```

### Block 8: push GOOD code, which should be MERGED (Window C)
```powershell
cd $env:TEMP\demo-live
git checkout main; git pull
$b = "feature/RC3-10-class-full-$(Get-Date -Format HHmmss)"
git checkout -b $b
@"


CLASS_FULL = "Class full"


def book_if_space(gym_class, membership_number):
    """When a class reaches its capacity, members see the message "Class full".
    A member cannot book a class that is full."""
    if len(gym_class.bookings) >= gym_class.capacity:
        return CLASS_FULL
    gym_class.bookings.append(membership_number)
    return "Booked"
"@ | Add-Content booking.py
git commit -am "RC3-10 class full message"
git push -u origin HEAD
```

### Block 9: push INCOMPLETE code, which should FAIL (Window C)
```powershell
cd $env:TEMP\demo-live
git checkout main; git pull
$b = "feature/RC3-8-booking-window-$(Get-Date -Format HHmmss)"
git checkout -b $b
@"


def can_book_draft(gym_class, now):
    return now < gym_class.start_time
"@ | Add-Content booking.py
git commit -am "RC3-8 booking window draft"
git push -u origin HEAD
```

### Block 10: fix the failed branch, then push again; it should be re-reviewed and MERGED (Window C, right after Block 9)
```powershell
cd $env:TEMP\demo-live
@"


from datetime import timedelta


def can_book_7_days(gym_class, now):
    """Members can book a class up to 7 days before it starts.
    Booking more than 7 days before the class starts is refused."""
    return now < gym_class.start_time and gym_class.start_time - now <= timedelta(days=7)
"@ | Add-Content booking.py
git commit -am "RC3-8 enforce the 7-day booking window"
git push
```

### Block 11: push with NO ticket key, which should be BLOCKED (Window C)
```powershell
cd $env:TEMP\demo-live
git checkout main; git pull
git checkout -b "fix-typo-$(Get-Date -Format HHmmss)"
Add-Content README.md "typo fix"
git commit -am "fix typo"
git push -u origin HEAD
```

### Block 12: see the results (Window C)
```powershell
gh pr list -R umarahad2005/rc3-pr-reviewer-demo --state all --limit 10
$n = gh pr list -R umarahad2005/rc3-pr-reviewer-demo --state all --limit 1 --json number --jq '.[0].number'
gh pr view $n -R umarahad2005/rc3-pr-reviewer-demo --comments
start https://github.com/umarahad2005/rc3-pr-reviewer-demo/pulls?q=is%3Apr
```
Each PR should have **exactly one** "AI review" comment per push.

### Block 13 (alternative to Blocks 3–5): automation without ngrok (Window A)
```powershell
cd C:\Users\umara\Downloads\RC3_AI_HACK\task4_trackA
Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
$env:GITHUB_TOKEN = (gh auth token)
python cli.py watch --repo umarahad2005/rc3-pr-reviewer-demo --interval 10
```
Then run Blocks 8–12 as before. Use either `serve` + ngrok **or** `watch`, never both.

### Block 14: before you zip and submit
```powershell
cd C:\Users\umara\Downloads\RC3_AI_HACK\task4_trackA
python -m pytest -q *> demo\tests_offline.txt
$k = $env:GEMINI_API_KEY; if ($k) { (Get-ChildItem -Recurse -File -Exclude .env | Select-String -SimpleMatch -Pattern $k).Count }
Compress-Archive -Path (Get-ChildItem -Force | Where-Object { $_.Name -notin '.env','__pycache__','.pytest_cache','.watch_state.json' }) -DestinationPath ..\task4_trackA_submission.zip -Force
```
The secret check must print `0`. The zip leaves out `.env`.

---

## 0. Prerequisites (check once)
```powershell
python --version            # 3.10+ (built with 3.12)
git --version
gh --version                # GitHub CLI
gh auth status              # must say "Logged in to github.com"
ngrok version               # only needed for live GitHub webhooks (section 8)
```
If `gh` is not logged in:
```powershell
gh auth login
```
If ngrok is missing or too old (the minimum is 3.28):
```powershell
winget install --id Ngrok.Ngrok -e
ngrok update
```

## 1. One-time setup
```powershell
cd C:\Users\umara\Downloads\RC3_AI_HACK\task4_trackA
pip install -r requirements.txt          # requests, google-genai, pytest
pip install pypdf                        # only for importing .pdf tickets
Copy-Item .env.example .env
notepad .env
```

### `.env` values
| Variable | Required? | Value |
|---|---|---|
| `GEMINI_API_KEY` | **yes** | Your free key from https://aistudio.google.com → Get API key |
| `GEMINI_MODEL` | no | `gemini-flash-lite-latest` (worked on 2026-11-05). Alternatives: `gemini-3.5-flash`, `gemini-3-flash-preview` |
| `GITHUB_TOKEN` | **yes** | Leave empty in `.env` and load it from `gh` instead (below) |
| `JIRA_TICKETS_DIR` | one ticket source | `tickets/jira` (local Jira JSON files; used in the demo) |
| `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN` | one ticket source | Live Jira site, e.g. `https://yoursite.atlassian.net` |
| `TICKETS_CSV` | one ticket source | `tickets/clear_tickets_jira.csv` (the Task 1 output) |
| `WEBHOOK_SECRET` | for live webhooks | A random secret; generate it in section 8.2 |
| `MAX_DIFF_CHARS` | no | `60000`. Bigger diffs are blocked, never cut |

Ticket-source priority: **live Jira > `JIRA_TICKETS_DIR` > `TICKETS_CSV`**. Set only the one you want.

### GitHub token (in every new PowerShell window)
```powershell
$env:GITHUB_TOKEN = (gh auth token)
```
**Security rules:**
- Never paste keys, tokens or the webhook secret into a chat.
- Never commit `.env`; it is in `.gitignore`.
- Variables you set with `$env:` or `setx` override `.env`.

## 2. Offline tests (no network, no keys needed)
```powershell
python -m pytest -q                       # expect: 64 passed
python -m pytest -q tests\test_evaluator.py          # LLM verdict parsing and safety
python -m pytest -q tests\test_pipeline.py           # every BLOCK case and the MERGE path
python -m pytest -q tests\test_server.py             # webhook signature, events, health
python -m pytest -q tests\test_fetchers.py           # ticket ID, Jira and CSV sources, diff fetch
python -m pytest -q tests\test_local_jira.py         # local Jira files (v2, export, v3 ADF)
python -m pytest -q tests\test_autopilot_import.py   # importer and push automation
```
The tests ignore your `.env`, so they always run the same way.

## 3. CLI reference: every command and option
```powershell
python cli.py -h                          # list commands
python cli.py <command> -h                # options of one command
```
| Command | Options | What it does |
|---|---|---|
| `import-tickets` | `--inbox tickets/inbox` `--out tickets/jira` | Converts txt/md/pdf/docx/json/csv tickets to Jira JSON |
| `review` | `--repo OWNER/NAME` `--pr N` `[--dry-run]` | Reviews one PR now |
| `watch` | `--repo OWNER/NAME` `[--interval 15]` `[--dry-run]` `[--once]` `[--all]` | Polls GitHub; every new push gets a PR, a review and a merge or fail |
| `serve` | `[--port 8000]` `[--dry-run]` | Webhook listener: `POST /webhook`, `GET /health` |
| `replay` | `PAYLOAD.json` `[--url http://localhost:8000/webhook]` `[--event pull_request\|push]` | Sends a saved GitHub event to `serve`, signed if `WEBHOOK_SECRET` is set |

Extra tool:
```powershell
python csv_to_jira_json.py <tickets_jira.csv> <out folder>   # Task 1 CSV -> Jira JSON files
```

**Exit codes:**
- `review`: `0` = MERGE, `1` = BLOCK.
- `import-tickets`: `0` = all imported, `1` = some warnings.

## 4. Tickets: put them in, convert to Jira JSON

### 4.1 Supported formats (drop the files in `tickets\inbox\`)
| Format | Example in the repo |
|---|---|
| `.txt` / `.md` | `tickets\inbox\RC3-7.txt` |
| `.docx` (Word bullets, headings and ☐ checkboxes OK) | `tickets\inbox\RC3-8_booking_window.docx`, `tickets\inbox\RC3-20_configuration_apis.docx` |
| `.pdf` | `tickets\inbox\RC3-9.pdf` |
| `.json` | A Jira issue (`GET /rest/api/2/issue/KEY`) or a Jira search export `{"issues":[...]}` |
| `.csv` | Jira export or the Task 1 `tickets_jira.csv` (`tickets\inbox\task1_tickets_jira.csv`) |

### 4.2 What a ticket file must contain
```
Key: RC3-10                         <- or put the key in the file name, e.g. RC3-10.txt
Summary: Show class full message    <- or "Title:", or just the first line

Acceptance Criteria:                <- this heading is required
- When a class reaches its capacity, members see the message "Class full".
- A member cannot book a class that is full.
```
Bullets can be `-`, `*`, `•`, `1.` or Word list items.
- A file with **no key** is skipped with a warning.
- A ticket with **no acceptance criteria** is imported as "None given", and the reviewer will **never merge** it.

### 4.3 Create a ticket from PowerShell and import it
```powershell
@"
Key: RC3-10
Summary: Show class full message

Acceptance Criteria:
- When a class reaches its capacity, members see the message "Class full".
- A member cannot book a class that is full.
"@ | Set-Content tickets\inbox\RC3-10.txt -Encoding utf8

python cli.py import-tickets                                   # default folders
python cli.py import-tickets --inbox C:\path\to\sir_tickets --out tickets\jira   # any folder
dir tickets\jira
type tickets\jira\RC3-10.json
```

### 4.4 Other ways to get tickets
```powershell
# Task 1 CSV -> Jira JSON
python csv_to_jira_json.py ..\task1\out\clear\tickets_jira.csv tickets\jira

# Save a real Jira ticket as a file: open this URL in a logged-in browser and save the page
#   https://<site>.atlassian.net/rest/api/2/issue/RC3-5   ->  tickets\jira\RC3-5.json
```
Live Jira instead of files: put `JIRA_BASE_URL`, `JIRA_EMAIL` and `JIRA_API_TOKEN` in `.env`. The token comes from https://id.atlassian.com/manage-profile/security/api-tokens.

## 5. Review a single PR manually
```powershell
# Preview: prints every stage, the decision and the actions; changes nothing on GitHub
python cli.py review --repo umarahad2005/rc3-pr-reviewer-demo --pr 5 --dry-run

# Real: sets the status, comments, and merges if fulfilled
python cli.py review --repo umarahad2005/rc3-pr-reviewer-demo --pr 5
echo $LASTEXITCODE                        # 0 = merged, 1 = blocked
```
The PR's **branch name or title must contain the ticket key**, for example `feature/RC3-10-class-full` or `RC3-10 Class full`.

Output stages:
```
[1/6 webhook]   PR title, branch, SHA
[2/6 story]     ticket ID, ticket title, source, number of AC
[3/6 code]      diff size
[4/6 llm]       fulfilled=True/False
[5/6 decision]  MERGE / BLOCK + reason
[6/6 action]    status + comment (+ merge)
```

## 6. Full automation, local (no public URL): `watch`
**Window A** (the reviewer; leave it running):
```powershell
cd C:\Users\umara\Downloads\RC3_AI_HACK\task4_trackA
$env:GITHUB_TOKEN = (gh auth token)
python cli.py import-tickets
python cli.py watch --repo umarahad2005/rc3-pr-reviewer-demo --interval 10
```
Options:
- `--dry-run`: decide only, do nothing.
- `--once`: one check, then exit.
- `--all`: also review branches that existed before you started.
- `--interval N`: seconds between checks.
- **Ctrl+C** stops it.

Watch remembers what it has reviewed in `.watch_state.json`. Delete that file to start fresh:
```powershell
Remove-Item .watch_state.json -ErrorAction SilentlyContinue
```
Then push code from Window B (section 9). **Do not run `watch` and `serve` at the same time**, or each push is reviewed twice.

## 7. Webhook mode without GitHub (local replay)
```powershell
# Window A
python cli.py serve --port 8000                  # add --dry-run to change nothing on GitHub

# Window B
Invoke-RestMethod http://localhost:8000/health   # -> ok: True
python cli.py replay demo\payload_pr1_opened.json --url http://localhost:8000/webhook
python cli.py replay demo\payload_pr1_opened.json --event pull_request
```
`replay` signs the payload with `WEBHOOK_SECRET` from `.env`, just as GitHub does.

## 8. Full automation, live GitHub webhook (ngrok)

### 8.1 ngrok, once
1. Sign up free at https://dashboard.ngrok.com/signup.
2. Copy your token from https://dashboard.ngrok.com/get-started/your-authtoken.
3. Run:
   ```powershell
   ngrok config add-authtoken <your-ngrok-token>
   ngrok update
   ```

### 8.2 Webhook secret, once
```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```
Put the output in `.env` as `WEBHOOK_SECRET=<value>`, and in GitHub (8.4). Never share it.

### 8.3 Start the server and the tunnel
```powershell
# Window A: server
cd C:\Users\umara\Downloads\RC3_AI_HACK\task4_trackA
$env:GITHUB_TOKEN = (gh auth token)
python cli.py serve --port 8000

# Window B: tunnel (keep it open)
ngrok http 8000
```
Copy the `Forwarding https://<name>.ngrok-free.dev` URL **exactly**. To print it from another window:
```powershell
(Invoke-RestMethod http://127.0.0.1:4040/api/tunnels).tunnels.public_url
```

### 8.4 GitHub webhook settings
Open https://github.com/umarahad2005/rc3-pr-reviewer-demo/settings/hooks, then **Add webhook** (or **Edit**):

| Field | Value |
|---|---|
| Payload URL | `https://<your-exact-ngrok-name>.ngrok-free.dev/webhook` (must end with `/webhook`) |
| Content type | `application/json` |
| Secret | The same value as `WEBHOOK_SECRET` in `.env` |
| SSL verification | Enable |
| Events | "Let me select individual events": ✅ **Pushes** ✅ **Pull requests** |
| Active | ✅ |

### 8.5 Check the webhook
On GitHub, open the webhook, then **Recent Deliveries**, then the ping, and click **Redeliver**.

| Response | Meaning / fix |
|---|---|
| **200** | Working |
| **401** `invalid signature` | Secret mismatch: make GitHub and `.env` identical, then restart `serve` |
| **404** with `ERR_NGROK_3200` | The Payload URL is not your live ngrok URL (typo, or ngrok restarted with a new name) |
| **404** from the server | The URL does not end with `/webhook` |
| **502** | `serve` is not running |

Check from the command line:
```powershell
$h = gh api repos/umarahad2005/rc3-pr-reviewer-demo/hooks --jq '.[0].id'
gh api repos/umarahad2005/rc3-pr-reviewer-demo/hooks/$h --jq '.config.url'
gh api "repos/umarahad2005/rc3-pr-reviewer-demo/hooks/$h/deliveries?per_page=5" --jq '.[] | "\(.delivered_at) \(.event) \(.status_code)"'
```
The ngrok inspector at http://127.0.0.1:4040 shows every request.

### 8.6 How events are handled
- **Push to a branch with no PR:** the tool opens a PR and reviews it once.
- **Push to a branch that already has an open PR:** the push is skipped, and GitHub's `pull_request/synchronize` event does the review.
- **`pull_request/opened` for a PR the tool opened itself:** skipped, because the push already reviewed it.
- **Push to `main`:** ignored.

After changing the code, restart `serve` (Ctrl+C, then `python cli.py serve --port 8000`).

## 9. Demo script (Window B = the developer)
```powershell
cd $env:TEMP
gh repo clone umarahad2005/rc3-pr-reviewer-demo demo-live
cd demo-live
```

### 9.1 GOOD code → MERGED (ticket RC3-10 from section 4.3)
```powershell
git checkout main; git pull
git checkout -b feature/RC3-10-class-full
@"


CLASS_FULL = "Class full"


def book_if_space(gym_class, membership_number):
    """When a class reaches its capacity, members see the message "Class full".
    A member cannot book a class that is full."""
    if len(gym_class.bookings) >= gym_class.capacity:
        return CLASS_FULL
    gym_class.bookings.append(membership_number)
    return "Booked"
"@ | Add-Content booking.py
git commit -am "RC3-10 class full message"
git push -u origin HEAD
```
Expect: a PR is opened, then `fulfilled=True`, then `decision=MERGE`, and the PR is **Merged**.

### 9.2 INCOMPLETE code → FAILED
```powershell
git checkout main; git pull
git checkout -b feature/RC3-8-booking-window-v2
@"


def can_book(gym_class, now):
    return now < gym_class.start_time
"@ | Add-Content booking.py
git commit -am "RC3-8 booking window"
git push -u origin HEAD
```
Expect: `fulfilled=False`, then `decision=BLOCK`, a red ✗ Failed status, and a comment saying the 7-day rule is missing.

### 9.3 Fix the failed PR by pushing again → re-reviewed
```powershell
@"


from datetime import timedelta


def can_book_7_days(gym_class, now):
    """Members can book a class up to 7 days before it starts.
    Booking more than 7 days before the class starts is refused."""
    return now < gym_class.start_time and gym_class.start_time - now <= timedelta(days=7)
"@ | Add-Content booking.py
git commit -am "RC3-8 enforce 7-day booking window"
git push
```
Expect: the same PR is reviewed again. If the criteria are now met, it is **Merged**.

### 9.4 No ticket key → BLOCKED (safety)
```powershell
git checkout main; git pull
git checkout -b fix-typo
Add-Content README.md "typo fix"
git commit -am "fix typo"
git push -u origin HEAD
```
Expect: `no ticket ID in branch or title`, then `decision=BLOCK`. No AI call and no merge.

### 9.5 Ticket without acceptance criteria → BLOCKED (safety)
```powershell
"Key: RC3-11`nSummary: Something vague`n`nPlease improve the app." | Set-Content C:\Users\umara\Downloads\RC3_AI_HACK\task4_trackA\tickets\inbox\RC3-11.txt
cd C:\Users\umara\Downloads\RC3_AI_HACK\task4_trackA; python cli.py import-tickets; cd $env:TEMP\demo-live
git checkout main; git pull; git checkout -b feature/RC3-11-vague
Add-Content booking.py "`n# RC3-11"
git commit -am "RC3-11 vague"
git push -u origin HEAD
```
Expect: `decision=BLOCK`, reason "Ticket RC3-11 has no acceptance criteria; cannot verify the PR."

## 10. See the results
```powershell
gh pr list -R umarahad2005/rc3-pr-reviewer-demo --state all
gh pr view <N> -R umarahad2005/rc3-pr-reviewer-demo --comments
gh pr view <N> -R umarahad2005/rc3-pr-reviewer-demo --json state,mergedAt,statusCheckRollup
start https://github.com/umarahad2005/rc3-pr-reviewer-demo/pulls?q=is%3Apr
```
- **Merged** PR: green ✓ `ai-pr-reviewer` and a "AI review: PASSED" comment.
- **Blocked** PR: red ✗ `ai-pr-reviewer` and a "AI review: FAILED - merge blocked" comment.

To make the red ✗ truly block the Merge button for people too:
1. Repo Settings → Branches → Add rule for `main`.
2. Tick ✅ "Require status checks to pass before merging".
3. Add `ai-pr-reviewer` as the required check.

## 11. Save demo evidence
```powershell
python cli.py review --repo umarahad2005/rc3-pr-reviewer-demo --pr 5 --dry-run *> demo\my_run_pr5.txt
python cli.py watch --repo umarahad2005/rc3-pr-reviewer-demo --once *> demo\my_watch_once.txt
python -m pytest -q *> demo\tests_offline.txt
gh pr list -R umarahad2005/rc3-pr-reviewer-demo --state all *> demo\pr_list.txt
```

## 12. When the tool will NOT merge (all covered by tests)
| Situation | Result |
|---|---|
| No ticket key in the branch or title | BLOCK |
| Ticket not found, or the ticket source fails | BLOCK |
| Ticket has no acceptance criteria | BLOCK |
| Diff empty, or larger than `MAX_DIFF_CHARS` | BLOCK (never cut) |
| LLM error, reply not JSON, or `fulfilled` missing or not a boolean | BLOCK |
| LLM says `fulfilled: false` | BLOCK, with the list of missing items |
| The merge API call fails | Reported as BLOCK |

## 13. Troubleshooting
| Problem | Fix |
|---|---|
| `GEMINI_API_KEY not set` | Fill it in `.env`, or `$env:GEMINI_API_KEY="..."` in your own window |
| LLM 429 / 503 / 403 / 404 model | Change `GEMINI_MODEL` in `.env` to `gemini-flash-lite-latest` or `gemini-3.5-flash` |
| GitHub 401 / 403 | Run `$env:GITHUB_TOKEN = (gh auth token)` again; check `gh auth status` |
| `Ticket ... not found` | Run `python cli.py import-tickets`; check that `tickets\jira\<KEY>.json` exists and `JIRA_TICKETS_DIR=tickets/jira` |
| Nothing happens after a push (`watch`) | The branch name must contain the key; Window A must still be running |
| Nothing happens after a push (webhook) | Check Recent Deliveries (section 8.5); restart `serve`; check the ngrok URL |
| Two review comments on one PR | `watch` and `serve` were both running, or the old `serve` is still running: stop one and restart `serve` |
| `ngrok` "agent version too old" (ERR_NGROK_121) | `ngrok update` |
| `git push` says the branch exists | Use a new branch name, e.g. `feature/RC3-10-class-full-2` |
| pdf import error | `pip install pypdf` |

## 14. Clean up after the demo
```powershell
# stop serve / watch / ngrok with Ctrl+C in their windows
Remove-Item .watch_state.json -ErrorAction SilentlyContinue
# optional: delete the GitHub webhook (Settings -> Webhooks -> Delete) and the test repo
gh repo delete umarahad2005/rc3-pr-reviewer-demo     # only when you no longer need the demo
```
Check that no secret is inside the folder before you zip it. This must print `0`:
```powershell
$k = $env:GEMINI_API_KEY; (Get-ChildItem -Recurse -File -Exclude .env | Select-String -SimpleMatch -Pattern $k).Count
```
**Do not include `.env` in the zip.** Only `.env.example` belongs there.

## 15. Saved demo evidence (in `demo/`)
| File | Shows |
|---|---|
| `run_pr1_failed_via_webhook.txt`, `server_log_pr1.txt` | PR #1 incomplete → **Failed** with a comment (replayed webhook) |
| `run_pr2_merged.txt` | PR #2 complete → **Merged** |
| `run_pr3_no_ticket_blocked.txt` | PR #3 no ticket key → blocked |
| `run_pr1_local_jira_dryrun.txt` | Ticket read from the local Jira file `tickets/jira/TASK-004.json` |
| `import_tickets_log.txt` | txt, docx, pdf and csv tickets → Jira JSON |
| `watch_log.txt`, `github_state_push_demo.json` | Push → PR #4 opened automatically → **Merged**; push → PR #5 → **Failed** |
| `github_webhook_push_flow.txt` | **Live GitHub webhook via ngrok:** push → PR #6 opened → **Merged** (HTTP 200) |
| `github_state_pr1.json`, `github_state_pr2.json` | GitHub's own record of the statuses and the merge |
| `tests_offline.txt` | pytest: 64 passed |

See `README.md` for the design and `CONTRACT.md` for the module interfaces.

---

## 16. Sir's ticket + sir's code: run them live

Sir gives you one ticket and one piece of code. The ticket goes in as a Jira ticket and the code goes up as a PR. The tool reviews the code against the ticket's acceptance criteria, then **merges** the PR or **blocks** it with a comment.

### Step 0: setup (Window A)
```powershell
cd C:\Users\umara\Downloads\RC3_AI_HACK\task4_trackA
$env:GITHUB_TOKEN = (gh auth token)
```

### Step 1: put sir's ticket in the inbox (Window A)
If sir's ticket has no key, make one up (for example `RC3-20`). The `Acceptance Criteria:` heading is required, otherwise the tool never merges.
```powershell
@"
Key: RC3-20
Summary: <sir's ticket title>

Acceptance Criteria:
- <criterion 1 from sir's ticket>
- <criterion 2 from sir's ticket>
"@ | Set-Content tickets\inbox\RC3-20.txt -Encoding utf8

python cli.py import-tickets
type tickets\jira\RC3-20.json
```
If sir gives a `.docx`, `.pdf` or `.csv`, copy it into `tickets\inbox\` with the key in the file name (for example `RC3-20.docx`), then run `python cli.py import-tickets`.

### Step 2: push sir's code as a PR (Window B)
The **branch name must contain the ticket key**.
```powershell
cd $env:TEMP
if (-not (Test-Path demo-live)) { gh repo clone umarahad2005/rc3-pr-reviewer-demo demo-live }
cd $env:TEMP\demo-live
git checkout main; git pull
git checkout -b feature/RC3-20-sir-code
Copy-Item C:\path\to\sir_code.py .\sir_code.py     # or paste sir's code into a new file
git add sir_code.py
git commit -m "RC3-20 sir's code"
git push -u origin HEAD
gh pr create --title "RC3-20 sir's code" --body "Review against RC3-20" --base main
```

### Step 3: run the reviewer (Window A)
Safe preview first. It prints all 6 stages and the decision, and changes nothing on GitHub:
```powershell
$n = gh pr list -R umarahad2005/rc3-pr-reviewer-demo --limit 1 --json number --jq '.[0].number'
python cli.py review --repo umarahad2005/rc3-pr-reviewer-demo --pr $n --dry-run
```
Real run. It sets the status, posts the comment, and merges if the code passes:
```powershell
python cli.py review --repo umarahad2005/rc3-pr-reviewer-demo --pr $n
```

### Step 4: show sir the result
```powershell
gh pr view $n -R umarahad2005/rc3-pr-reviewer-demo --comments
start "https://github.com/umarahad2005/rc3-pr-reviewer-demo/pull/$n"
```

### What sir sees
```
[1/6 webhook]  PR title, branch, SHA
[2/6 story]    RC3-20 found, N acceptance criteria
[3/6 code]     diff size
[4/6 llm]      fulfilled=True / False
[5/6 decision] MERGE or BLOCK + reason
[6/6 action]   status ai-pr-reviewer + comment (+ squash-merge)
```
- **Code meets every criterion:** status Success, an "AI review" comment, and the PR is **merged**.
- **Code misses something:** status Failed, and a comment listing what is missing. It is **not merged**.

**Optional fully automatic version:** skip `gh pr create` and Step 3. Run `python cli.py watch --repo umarahad2005/rc3-pr-reviewer-demo --interval 10` in Window A, then push the branch. Watch creates the PR and reviews it on its own. Do not run `watch` and `serve` at the same time.

---

## 17. Demo with the real Jira ticket doc + the 2 code files (RC3-20)

**Inputs:**
| File | What it is |
|---|---|
| `tickets\inbox\RC3-20_configuration_apis.docx` | The Jira ticket "Configuration Management APIs" (9 acceptance criteria). The key `RC3-20` comes from the file name, because the doc has none. (It was moved here from `tickets\jira\`, since the importer reads `tickets\inbox\` only.) |
| `demo\userController.js` | Code file 1 (the full user controller) |
| `demo\WUserController.js` | Code file 2 (the user controller with registration and email verification removed) |

**Expected result:** both PRs are **BLOCKED** (Failed + comment). Both files are user/auth controllers. Neither one implements the configuration CRUD (`addNewConfiguration`, `getAllConfigurations`, ...) that RC3-20 asks for. A local check gave: `fulfilled=false`, "WUserController.js deals with user registration, authentication... completely misses the Configuration Management APIs required by RC3-20". This shows the reviewer refusing code that does not match the ticket.

### Step 1: import the ticket (Window A)
```powershell
cd C:\Users\umara\Downloads\RC3_AI_HACK\task4_trackA
$env:GITHUB_TOKEN = (gh auth token)
python cli.py import-tickets
type tickets\jira\RC3-20.json
```
Expect: `RC3-20_configuration_apis.docx -> tickets/jira\RC3-20.json (9 acceptance criteria)`.

### Step 2: start the automation (Window A, leave it running)
```powershell
Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
python cli.py watch --repo umarahad2005/rc3-pr-reviewer-demo --interval 10
```
(Or use `serve` + ngrok, Blocks 3–5. Never run both.)

### Step 3: push code file 1, userController.js (Window B)
```powershell
cd $env:TEMP
if (-not (Test-Path demo-live)) { gh repo clone umarahad2005/rc3-pr-reviewer-demo demo-live }
cd $env:TEMP\demo-live
git checkout main; git pull
git checkout -b "feature/RC3-20-userController-$(Get-Date -Format HHmmss)"
New-Item -ItemType Directory -Force controllers | Out-Null
Copy-Item C:\Users\umara\Downloads\RC3_AI_HACK\task4_trackA\demo\userController.js controllers\userController.js
git add controllers\userController.js
git commit -m "RC3-20 configuration APIs (userController.js)"
git push -u origin HEAD
```
Watch (Window A) opens the PR and reviews it. Expect `fulfilled=False`, `decision=BLOCK`, a red ✗, and a comment that the configuration endpoints are missing.

### Step 4: push code file 2, WUserController.js (Window B)
```powershell
cd $env:TEMP\demo-live
git checkout main; git pull
git checkout -b "feature/RC3-20-WUserController-$(Get-Date -Format HHmmss)"
New-Item -ItemType Directory -Force controllers | Out-Null
Copy-Item C:\Users\umara\Downloads\RC3_AI_HACK\task4_trackA\demo\WUserController.js controllers\WUserController.js
git add controllers\WUserController.js
git commit -m "RC3-20 configuration APIs (WUserController.js)"
git push -u origin HEAD
```
Expect: BLOCK, with the same kind of comment.

### Step 5: see the results (Window B)
```powershell
gh pr list -R umarahad2005/rc3-pr-reviewer-demo --state all --limit 5
$n = gh pr list -R umarahad2005/rc3-pr-reviewer-demo --state all --limit 1 --json number --jq '.[0].number'
gh pr view $n -R umarahad2005/rc3-pr-reviewer-demo --comments
start https://github.com/umarahad2005/rc3-pr-reviewer-demo/pulls?q=is%3Apr
```

### Without `watch` (manual: one PR at a time)
After the `git push` in Step 3 or 4:
```powershell
gh pr create -R umarahad2005/rc3-pr-reviewer-demo --title "RC3-20 configuration APIs" --body "Review against RC3-20" --base main
$n = gh pr list -R umarahad2005/rc3-pr-reviewer-demo --limit 1 --json number --jq '.[0].number'
cd C:\Users\umara\Downloads\RC3_AI_HACK\task4_trackA
python cli.py review --repo umarahad2005/rc3-pr-reviewer-demo --pr $n --dry-run   # preview, changes nothing
python cli.py review --repo umarahad2005/rc3-pr-reviewer-demo --pr $n             # real: status + comment (+ merge)
echo $LASTEXITCODE                                                                   # 1 = blocked
```

### Save the evidence
```powershell
cd C:\Users\umara\Downloads\RC3_AI_HACK\task4_trackA
python cli.py import-tickets *> demo\import_rc3_20_log.txt
python cli.py review --repo umarahad2005/rc3-pr-reviewer-demo --pr $n --dry-run *> demo\run_rc3_20_review.txt
gh pr list -R umarahad2005/rc3-pr-reviewer-demo --state all *> demo\pr_list.txt
```

**If you see `503 UNAVAILABLE`:** Gemini is busy, so the tool blocks safely. Run the `review` again, or set `GEMINI_MODEL=gemini-3.5-flash` in `.env`.

---

## 18. One command: `python start.py` (start once, then just push)

```powershell
cd C:\Users\umara\Downloads\RC3_AI_HACK\task4_trackA
python start.py                 # LIVE: status, comment, and merge if the code passes
python start.py --dry-run       # decide only, change nothing on GitHub
python start.py --repo owner/name --interval 10
```
`start.py` does every setup step and then keeps running until **Ctrl+C**:
1. **GitHub token:** uses `GITHUB_TOKEN` from `.env` if it can access the repo; otherwise it uses `gh auth token` automatically. No `$env:GITHUB_TOKEN` line is needed.
2. **Gemini key:** checks that `GEMINI_API_KEY` is set (the key is never printed).
3. **Tickets:** imports everything in `tickets\inbox\` into `tickets\jira\`.
4. **Watch:** every push to a branch with a ticket key (for example `feature/RC3-20-x`) opens a PR, reviews it, and then MERGEs or BLOCKs it.

In a second window, just push:
```powershell
cd $env:TEMP\demo-live
git checkout main; git pull
git checkout -b feature/RC3-20-sir-code
# add sir's code
git add -A; git commit -m "RC3-20 sir's code"; git push -u origin HEAD
```
No ngrok and no `gh pr create` are needed. Watch polls GitHub every 10 seconds. A new ticket dropped in `tickets\inbox\` is picked up the next time you start `start.py`. Do not run it at the same time as `serve` or `watch`.
