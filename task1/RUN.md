# How to run Task 1: Brief2Jira

This tool turns a client brief into a breakdown, Jira tickets and open questions. It never assumes anything the brief does not say.

## 1. One-time setup (PowerShell)
```powershell
cd C:\Users\umara\Downloads\RC3_AI_HACK\task1
pip install google-genai pytest
Copy-Item .env.example .env
notepad .env
```
In `.env`, set `GEMINI_API_KEY=<your key>` and save the file. Get a free key from https://aistudio.google.com → Get API key.

- Never paste the key into a chat, and never commit `.env`.
- A key set with `setx GEMINI_API_KEY "..."` or `$env:GEMINI_API_KEY` overrides `.env`.

## 2. Run the offline tests (no API calls)
```powershell
python -m pytest -q          # expect: 80 passed
```

## 3. Run the tool
```powershell
python main.py briefs\clear.txt --out out\clear     # well-specified gym booking brief
python main.py briefs\vague.txt --out out\vague     # vague grocery brief with 8 traps
python main.py <any brief.txt> --out out\mybrief    # your own brief
```
Optional: `--model gemini-3.5-flash` overrides `GEMINI_MODEL`. The default in `.env.example` is `gemini-flash-lite-latest`.
The saved demo outputs were made with:
```powershell
$env:GEMINI_THINKING_BUDGET="1024"; python main.py briefs\clear.txt --out out\clear --model gemini-3-flash-preview
```

## 4. Outputs (in the `--out` folder)
| File | Content |
|---|---|
| `run.log` | Exact copy of the console output: every ticket in full, each acceptance criterion next to its quote, the questions grouped by category, rejected items, lint warnings and counts |
| `tickets.json` | Tickets, general questions, rejected items and warnings |
| `tickets_jira.csv` | Jira import file with the columns `Summary, Issue Type, Description, Priority, Labels` |

## 5. Exit codes
| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Brief is empty or unreadable (checked before any API call) |
| 2 | `GEMINI_API_KEY` is not set |
| 3 | An LLM stage failed: quota (429), overload (503), truncation, or bad JSON. The error is in `failed_run.log`; earlier good outputs are kept. Wait a minute and re-run, or try another `--model` |

## 6. Edge-case checks
```powershell
python main.py tests\edge\empty.txt                     # exit 1
python main.py tests\edge\short.txt --out out\edge_short # "Build an app." -> mostly questions
cmd /c "set GEMINI_API_KEY=&& python main.py briefs\clear.txt"   # exit 2 (only if no .env key)
echo $LASTEXITCODE
```

## 7. Import into Jira
1. Jira → Settings → System → External system import → CSV, and pick `tickets_jira.csv`.
2. Use a **team-managed** project, or in a company-managed project map Summary → Epic Name for the Epic rows.
3. Leave Priority unmapped for blank rows. The authoritative value is in the Description's `h3. Details` line.

See `README.md` for the design and `TESTING.md` for the test results.
