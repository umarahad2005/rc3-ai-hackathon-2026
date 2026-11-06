# Task 4 (Track B): Stage Prompts for the Graded AI Chat

Ready-to-paste prompts for building `analyze.py` stage by stage in the graded chat. Total budget is about 2 hours.

**How to use this file**
1. Paste the stage prompt exactly as written. Each prompt carries its own context, so it works in a fresh turn.
2. Save the code it returns into `task4/`, then run the PowerShell tests.
3. Paste the **real terminal output** back into the chat. If anything is wrong, use the "focused fix" template. Never just say "it works".
4. Tick the done-checklist, then move on. If a stage overruns its time box, use the **Cut list**.

All commands assume this setup:
```powershell
cd C:\Users\umara\Downloads\RC3_AI_HACK\task4
# Without a token you get 60 GitHub calls/hour and will be blocked around Stage 3-4.
# Create a fine-grained token (public repos, no scopes) at github.com/settings/tokens, then:
$env:GITHUB_TOKEN = "<token>"    # never paste the token into the chat
```

| Stage | What | Time box | Running total |
|---|---|---|---|
| 0 | Token setup + planning prompt | 7 min | 0:07 |
| 1 | CLI + GitHub client | 15 min | 0:22 |
| 2 | Fetch bundle + tech stack | 12 min | 0:34 |
| 3 | File structure | 13 min | 0:47 |
| 4 | Complexity score | 12 min | 0:59 |
| 5 | Dependency health | 13 min | 1:12 |
| 6 | Contribution activity | 15 min | 1:27 |
| 7 | Combine, README, demo | 15 min | 1:42 |
| - | Failure demo + export | 10 min | 1:52 |

---

## Stage 0: Token setup + planning prompt (7 min)

**Goal:** get the architecture into the chat record before any code is written. This shows the grader a plan-first workflow.

```text
I'm doing RC3 AI Hackathon Task 4, Track B: a GitHub Repository Analyzer CLI.
Command: python analyze.py <github-repo-url>. It prints a terminal report with 5 sections:
1) Tech stack, with evidence for each item  2) File structure summary
3) Code complexity score, with the formula explained  4) Dependency health, with a definition of "healthy"
5) Contribution activity chart in the terminal (commits per week + top contributors).

Constraints: Python 3.12, ONLY requests + rich + the standard library. Optional GITHUB_TOKEN read from the
environment, never hard-coded. Allowed APIs: the GitHub REST API, PyPI JSON (https://pypi.org/pypi/{name}/json)
and the npm registry (https://registry.npmjs.org/{name}/latest). Never invent data: if something is missing,
print "Not available: <reason>". The user runs Windows PowerShell.

Planned architecture (review it, but do NOT write code yet):
- analyze.py: CLI and exit codes
- analyzer/github_client.py: parse_repo_url, GitHubClient.get, error classes, token from env
- analyzer/fetch.py: fetch_bundle(), which makes every GitHub call exactly once
- analyzer/techstack.py, structure.py, complexity.py, activity.py: pure functions over the bundle
- analyzer/deps.py: analyze_deps(bundle), the only section that calls the registries
- analyzer/report.py: rendering only (rich)
Every section returns {"status": "ok"|"unavailable", "reason": str|None, ...}.

Please reply with: (a) any risks or gaps in this design (rate limits, empty repos, truncated trees,
202 from the stats endpoint), (b) a 7-stage build order, (c) the exact GitHub endpoints each section needs.
Keep it under 300 words. Don't guess at API behaviour you aren't sure of; say so instead.
```

**Check:** the reply mentions the 202 retry, `truncated` trees, 409 for empty repos, and rate limits. If it misses one, ask "You didn't cover X; how should we handle it?" That follow-up also counts as evidence of critical review.

**Done:** [ ] plan reply in chat  [ ] you pushed back on at least one point

---

## Stage 1: CLI + GitHub client (15 min)

**Goal:** URL parsing, an authenticated GET, clear errors and exit codes. No analysis yet.

```text
Context: RC3 Task 4 Track B, GitHub Repository Analyzer CLI (python analyze.py <repo-url>). Python 3.12,
use ONLY requests + rich + the standard library. Windows PowerShell user. Never invent data.

This stage: create task4/analyze.py and task4/analyzer/__init__.py + task4/analyzer/github_client.py.
Don't create or touch any other files.

Contract:
- parse_repo_url(url: str) -> tuple[str, str]   # (owner, repo)
  Accept: https://github.com/o/r, http://, trailing "/", ".git" suffix, /tree/<branch>/..., and no scheme
  ("github.com/o/r"). Anything else raises InvalidRepoURL with a message showing the expected form.
- Exceptions (all subclass AnalyzerError): InvalidRepoURL,
  RepoNotFound (404 on GET /repos/{o}/{r} only; other 404s raise AnalyzerError with status 404),
  AuthError (401, bad token),
  RateLimitError(reset_epoch: int) (403/429 when header X-RateLimit-Remaining == "0"; message shows the
  reset time as HH:MM UTC and suggests setting GITHUB_TOKEN), NetworkError (timeout/connection).
  403/429 with a retry-after header or "secondary rate limit" in the message -> RateLimitError (wait retry-after or 60 s).
  Any other 403 -> AnalyzerError carrying GitHub's "message" field.
- class GitHubClient: __init__ reads os.environ.get("GITHUB_TOKEN") (never hard-coded); headers
  Accept: application/vnd.github+json, User-Agent: rc3-repo-analyzer, plus Authorization: Bearer <token> if set.
  get(path, params=None) -> requests.Response with a 15 s timeout; raises the errors above. It must return
  202 and 409 responses to the caller unchanged (later stages handle them).
- analyze.py: argparse with one positional url. For now it calls GET /repos/{o}/{r} and prints full_name,
  description, default_branch, stargazers_count. Each error prints one red rich line, e.g.
  "Error: Repository not found: x/doesnotexist (check spelling, or it may be private)".
  Exit codes: 0 ok, 1 unexpected, 2 invalid URL, 3 not found, 4 rate limit, 5 bad token (401), 6 network.

Don't guess: if the API doesn't give a field, show "Not available". Return complete file contents.
```

**Test (PowerShell):**
```powershell
python analyze.py https://github.com/psf/requests
python analyze.py github.com/psf/requests.git/
python analyze.py https://github.com/psf/requests/tree/main/src
python analyze.py https://github.com/x/doesnotexist ; $LASTEXITCODE
python analyze.py not-a-url ; $LASTEXITCODE
$t=$env:GITHUB_TOKEN; $env:GITHUB_TOKEN="bad"; python analyze.py https://github.com/psf/requests; "exit=$LASTEXITCODE"; $env:GITHUB_TOKEN=$t
```

**Correct output:** the three valid forms all print `psf/requests` and `main`, matching github.com/psf/requests. Exit codes should be 3, 2 and 5. No Python traceback should appear anywhere.

**Focused fix template:**
```text
Stage 1 output below. Problem: <one sentence, e.g. "the .git + trailing slash form raises InvalidRepoURL">.
Fix ONLY that in <file>, change nothing else, and show the corrected function only.
<paste terminal output>
```

**Done:** [ ] 3 URL forms parse  [ ] 404, invalid-URL and 401 messages are clear  [ ] exit codes right  [ ] no traceback

---

## Stage 2: Fetch bundle + tech stack (12 min)

**Goal:** make every GitHub call once, then detect the stack with evidence.

```text
Context: RC3 Task 4 Track B, GitHub Repository Analyzer CLI. Python 3.12, ONLY requests + rich + stdlib.
Existing: analyzer/github_client.py with GitHubClient.get(path, params) -> Response (raises RepoNotFound,
AuthError, RateLimitError, NetworkError; returns 202/409 responses as-is).

This stage: create analyzer/fetch.py and analyzer/techstack.py, and update analyze.py to print the tech
stack section (a plain rich table is fine; the final report comes later). Don't touch other files.

fetch_bundle(client, owner, repo) -> dict with keys:
  "repo": JSON of /repos/{o}/{r}
  "languages": JSON of /repos/{o}/{r}/languages  ({lang: bytes}) or None;  "languages_error": str|None
  "tree": list of {"path","type","size"} from /git/trees/{default_branch}?recursive=1, or None
  "tree_truncated": bool;  "tree_error": str|None  (409 -> "Repository is empty")
  "files": {path: decoded text} for requirements.txt and package.json at the repo ROOT, fetched via
           /contents/{path} (base64) ONLY if that path exists in the tree
  "commit_activity": list|None and "activity_error": str|None from /stats/commit_activity; on 202 retry up
           to 5 times with backoff 1,2,3,4,5 s, then activity_error="GitHub is still computing statistics, try again in a minute"
  "contributors": list|None from /contributors?per_page=10;  "contributors_error": str|None
Only the /repos call may raise. Wrap every later call in try/except AnalyzerError and store str(e) in the
matching *_error key. After the first RateLimitError make no more calls; set every remaining *_error to
"GitHub rate limit reached (resets HH:MM UTC)". 204 -> data None, error "no data (empty repo)".
No section-specific logic in fetch.py.

detect_stack(bundle) -> {"status":"ok"|"unavailable","reason":str|None,
  "items":[{"name":str,"category":"language"|"framework"|"tool"|"build","evidence":str}]}
- Languages: from bundle["languages"] with % of bytes, e.g. evidence "GitHub languages API: 92.1% of bytes".
  Keep >= 1%.
- Frameworks: read names ONLY from the fetched bundle["files"] requirements.txt/package.json
  (react, express, next, vue, jest, django, flask...), with the file as evidence,
  e.g. {"name":"Express","category":"framework","evidence":"package.json dependencies: express ^4.19.2"}.
- pyproject.toml/setup.py/go.mod/Cargo.toml/pom.xml: presence only, category "build",
  evidence "file present: <path>". Dockerfile and .github/workflows/*.yml: category "tool", presence only.
- If items is empty after all rules: status "unavailable", reason "No languages or known manifest/tooling files detected".
Don't guess: no detection from the repo name or description. Return complete files.
```

**Test:**
```powershell
python analyze.py https://github.com/psf/requests
python analyze.py https://github.com/expressjs/express
python analyze.py https://github.com/octocat/Hello-World
```

**Check against GitHub:** the language percentages should match the language bar on the right of the repo page (to within about 0.5%). For express, open `package.json` on GitHub and confirm the listed framework and tools really appear there. Hello-World should be `unavailable` or show almost nothing, with no invented items.

**Focused fix template:** same as Stage 1. Name the item that is wrong and give the evidence that shows it is wrong (for example, "jest is listed but package.json has no jest").

**Done:** [ ] every item has evidence  [ ] percentages match GitHub  [ ] Hello-World makes nothing up  [ ] only one tree call (if unsure, add a temporary print in `get`)

---

## Stage 3: File structure summary (13 min)

```text
Context: RC3 Task 4 Track B, GitHub Repository Analyzer CLI. Python 3.12, ONLY requests + rich + stdlib.
analyzer/fetch.py returns a bundle with "tree" (list of {"path","type":"blob"|"tree","size"}) or None,
"tree_truncated": bool, "tree_error": str|None.

This stage: create analyzer/structure.py (pure function, no network calls) and print its result from
analyze.py. Don't touch other files.

summarize_structure(bundle) -> {"status":"ok"|"unavailable","reason":str|None,
  "total_files":int, "total_dirs":int, "max_depth":int, "total_size_bytes":int,
  "top_level":[{"name":str,"type":"dir"|"file","files":int}],      # dirs: file count beneath them
  "top_extensions":[{"ext":str,"count":int}],                       # top 8; "(none)" for no extension
  "notable":[str],     # present among: README*, LICENSE*, tests/ or test/, docs/, .github/workflows, Dockerfile
  "truncated":bool, "note":str|None}
- max_depth = the largest path.count("/") over blob paths (a root file = 0).
- If tree is None: status "unavailable", reason = tree_error.
- If truncated: still summarise, but set note "GitHub truncated the tree (very large repo); counts are lower bounds".
Don't guess. Return complete files.
```

**Test:** run `psf/requests` and `octocat/Hello-World`.
**Check against GitHub:** the top-level list should match the folder list on the repo home page. Hello-World should show 1 file (README), depth 0. Spot-check one directory's file count by clicking into it.
**Done:** [ ] top-level matches the web page  [ ] Hello-World shows 1 file  [ ] the truncation note path exists

---

## Stage 4: Complexity score (12 min)

```text
Context: RC3 Task 4 Track B, GitHub Repository Analyzer CLI. Python 3.12, ONLY requests + rich + stdlib.
Bundle has "tree" (list of {"path","type","size"}) and "languages" ({lang: bytes}).

This stage: create analyzer/complexity.py (pure function) and print it from analyze.py. Don't touch other files.

score_complexity(bundle) -> {"status","reason","score":float (0-100, 1 decimal),"band":str,
  "components":[{"name":str,"value":str,"points":float,"max":25}], "formula":str, "caveat":str}
Formula: 4 components x 25 points:
  size      = 25 * min(1, log10(max(files,1)) / 4)            # 10,000 files = full
  depth     = 25 * min(1, max_depth / 10)
  large     = 25 * min(1, (share of blobs > 100 KB) / 0.10)    # 10% big files = full
  spread    = 25 * min(1, (languages with >= 1% of bytes - 1) / 5), floor 0
Bands: <25 Low, 25-50 Moderate, 50-75 High, >=75 Very high.
Bands are half-open: 25<=s<50 Moderate, 50<=s<75 High. If languages is empty/unavailable, spread = 0 and
add the note "language data unavailable".
"formula" must be a human-readable explanation printed under the score.
caveat = "Heuristic based on file count, nesting, file sizes and language bytes from the GitHub API;
it does not measure lines of code or cyclomatic complexity."
If the tree is unavailable: status "unavailable" with the reason. Don't guess. Return complete files.
```

**Test:** run `psf/requests`, `expressjs/express` and `octocat/Hello-World`.
**Check:** the component points should add up to the score (within 0.1). Work one component out by hand from the Stage 3 numbers (for example, files=100 gives size 12.5). Hello-World should come out Low.
**Done:** [ ] the components sum to the score  [ ] the formula and caveat print  [ ] you checked one component by hand

---

## Stage 5: Dependency health (13 min)

```text
Context: RC3 Task 4 Track B, GitHub Repository Analyzer CLI. Python 3.12, ONLY requests + rich + stdlib.
Bundle has "files": {path: text} containing requirements.txt and/or package.json if present at the root.
Allowed registry APIs ONLY: https://pypi.org/pypi/{name}/json (info.version) and
https://registry.npmjs.org/{name}/latest (version). 10 s timeout each.
Registry calls use plain requests.get with no Authorization header (never send GITHUB_TOKEN to PyPI/npm).
Normalize PyPI names with re.sub(r"[-_.]+","-",name).lower(); encode scoped npm names as @scope%2Fname.

This stage: create analyzer/deps.py and print it from analyze.py. Don't touch other files.

analyze_deps(bundle) -> {"status","reason",
  "manifests":[str], "deps":[{"name","ecosystem":"pypi"|"npm","spec":str,"pinned":bool,
     "latest":str|None,"state":"up-to-date"|"outdated"|"unknown (range)"|"unknown (lookup failed)"|"unknown (unparsable)"}],
  "pinned_pct":float, "uptodate_pct_of_pinned":float, "healthy":bool|None,
  "definition":str, "note":str|None}
Rules:
- pinned = exact version: "pkg==1.2.3" for pip; bare "1.2.3" for npm (no ^ ~ > < * x or ranges).
- up-to-date = pinned version == the registry's latest. Unpinned -> "unknown (range)", but still show latest.
- requirements.txt: skip blank lines, # comments and -r/-e/--options; strip extras [..] and ; markers;
  lines you can't parse -> "unknown (unparsable)". package.json: dependencies + devDependencies.
- Look up at most 30: pinned deps first, then ranges. If more, note "Checked 30 of N; pinned checked first".
  If pinned deps were skipped, say "based on K of M pinned".
- definition = "Healthy = at least 80% of dependencies pinned to an exact version AND at least 80% of
  pinned dependencies on the latest release."
- No manifest -> status "unavailable", reason "No requirements.txt or package.json found at repo root".
- healthy = None only if the manifest has 0 deps ("Not applicable"). 0 pinned deps -> healthy False,
  note "no pinned dependencies".
Don't guess versions: if a lookup fails, the state is "unknown (lookup failed)". Return complete files.
```

**Test:** run `expressjs/express` (npm), `psf/requests` and `octocat/Hello-World`.
**Check against registries:** pick one dependency and open `https://www.npmjs.com/package/<name>` (or pypi.org/project/<name>). The latest version should match what the tool shows. Hello-World should say "Not available: No requirements.txt or package.json...". For psf/requests, if there is no root requirements.txt, it should honestly say unavailable. That is correct behaviour, not a bug.
**Done:** [ ] one version checked by hand  [ ] the definition prints  [ ] the 30-cap note works  [ ] the no-manifest message prints

---

## Stage 6: Contribution activity (15 min)

```text
Context: RC3 Task 4 Track B, GitHub Repository Analyzer CLI. Python 3.12, ONLY requests + rich + stdlib.
Bundle has "commit_activity": list of 52 {"week": unix_ts, "total": int, "days": [...]} or None,
"activity_error": str|None, "contributors": list of {"login","contributions"} or None, "contributors_error".

This stage: create analyzer/activity.py (pure) and print it from analyze.py. Don't touch other files.

analyze_activity(bundle) -> {"status","reason",
  "weeks":[{"week_start":"YYYY-MM-DD","commits":int}],   # last 12 weeks
  "total_52w":int, "active_weeks_52w":int,
  "top_contributors":[{"login":str,"commits":int}],      # top 5
  "contributors_reason":str|None, "note":str|None}
Rendering in analyze.py: a terminal bar chart, one line per week: "2026-08-10 | ████████ 14", bars scaled
to 40 chars using rich (block characters, no plotting libraries). Then a small table of top contributors.
- If commit_activity is None: weekly part "Not available: <activity_error>", but still show contributors.
- If all 52 weeks are 0: show the chart AND note "No commits in the last 52 weeks".
- Contributor counts are all-time (GitHub API); label them that way.
Don't guess. Return complete files.
```

**Test:** run `psf/requests`, then `octocat/Hello-World`. Run requests a second time if the first run said "still computing".
**Check against GitHub:** open `github.com/psf/requests/graphs/contributors` (or the Insights > Contributors page). Top logins should broadly match; exact counts and order may differ slightly (graph excludes merges, API is cached). Hello-World should show zero weeks plus the note.
**Done:** [ ] bars render in PowerShell  [ ] the 202 path prints an honest message  [ ] contributors match the web page

---

## Stage 7: Combine, README, demo files (15 min)

```text
Context: RC3 Task 4 Track B, GitHub Repository Analyzer CLI. Python 3.12, ONLY requests + rich + stdlib.
Existing section functions all return {"status":"ok"|"unavailable","reason",...}:
detect_stack, summarize_structure, score_complexity, analyze_deps, analyze_activity (signatures as
already written). fetch_bundle(client, owner, repo) gathers the data.

This stage:
1) Create analyzer/report.py: render(console, repo_meta, sections, token_used: bool) -> None. ONLY rendering: a header panel
   (full_name, description, default branch, stars, analysed-at UTC time, authenticated yes/no), then 5
   numbered rich Panels in order: 1 Tech Stack, 2 File Structure, 3 Code Complexity, 4 Dependency Health,
   5 Contribution Activity. Any section with status "unavailable" prints "Not available: <reason>".
2) Slim down analyze.py: parse -> client -> fetch_bundle -> sections -> render. Add an optional
   --save PATH flag: use Console(record=True) and console.save_text(PATH) after rendering.
   Keep the existing error handling and exit codes. At the start of main():
   if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8")
   (so redirected output on Windows does not crash on the bar characters).
3) Create task4/README.md: states "Track B: GitHub Repository Analyzer", libraries (requests, rich),
   install (pip install requests rich), how to run in PowerShell, optional $env:GITHUB_TOKEN, what each
   section means (complexity formula, healthy definition), known limits (60 req/h unauthenticated,
   truncated trees, 202 stats, 30-dependency cap, root manifests only).
Don't change the logic of the section modules. Don't guess. Return complete files.
```

**Test:**
```powershell
New-Item -ItemType Directory -Force demo | Out-Null
python analyze.py https://github.com/psf/requests --save demo/psf_requests.txt
python analyze.py https://github.com/expressjs/express --save demo/expressjs_express.txt
python analyze.py https://github.com/octocat/Hello-World --save demo/hello_world.txt
Get-Content demo/psf_requests.txt -TotalCount 40
```
**Check:** all 5 panels appear in order, the .txt files are readable, and no section shows a value you can't trace to the API.
**Done:** [ ] 5 panels  [ ] README states Track B  [ ] demo files saved

---

## Failure-case demo for the chat (5 min, do not skip)

Run these, then paste the output into the chat with a short prompt. They show robustness in front of the grader.

```powershell
python analyze.py not-a-url ; "exit=$LASTEXITCODE"
python analyze.py https://github.com/x/doesnotexist ; "exit=$LASTEXITCODE"
$t=$env:GITHUB_TOKEN; $env:GITHUB_TOKEN="bad"; python analyze.py https://github.com/psf/requests; "exit=$LASTEXITCODE"; $env:GITHUB_TOKEN=$t
python analyze.py https://github.com/octocat/Hello-World   # missing manifest -> "Not available"
```

Prompt to paste with that output:
```text
Here are the failure cases from my analyzer: invalid URL, repo not found, bad token (401), and a repo with
no dependency files. Check that each message is clear and actionable and that nothing is invented.
Also review the rate-limit branch in github_client.py: I can't safely trigger a real rate limit, so
explain what happens when GitHub returns 403 with X-RateLimit-Remaining: 0 and confirm the code shows the
reset time. Don't fake a rate-limit output.
```
**Be honest:** do not edit headers or mock a fake 403 and present it as a real run. If you want extra evidence, you may show `Invoke-RestMethod https://api.github.com/rate_limit` to display your remaining quota.

---

## Cut list if behind schedule

Drop items in this order. **Never drop testing or the failure demo.**
1. Extra tech-stack detectors (keep languages + package.json/requirements.txt + Dockerfile + workflows).
2. The `notable` list and extension stats in Structure (keep counts, depth and top level).
3. The `--save` flag. Instead, copy and paste terminal output into `demo/*.txt` by hand.
4. Dependency lookups for devDependencies (state the cut in the README).
5. The weekly chart drops to 8 weeks. Keep the contributors table.
6. Polish in report.py: plain `console.print` sections are fine.
**Never cut:** "Not available: <reason>" handling, the error messages and exit codes, the complexity formula text, the healthy definition, and the README "Track B" line.

---

## Demo evidence (final 5 min)

1. Confirm that `task4/demo/` has `psf_requests.txt`, `expressjs_express.txt` and `hello_world.txt` (plus `failures.txt` if you saved the failure run: first `$env:PYTHONUTF8 = "1"`, then `... *> demo/failures.txt`).
2. Paste one full report into the chat and ask: "Final check: does every number trace to an API response? List anything that looks invented."
3. Run `/export` in the chat and save the transcript next to `task4/` as your submission evidence.
4. Final tree: `analyze.py`, `analyzer/{__init__,github_client,fetch,techstack,structure,complexity,deps,activity,report}.py`, `README.md`, `demo/`, `plan/`.
