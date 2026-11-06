Track B: GitHub Repository Analyzer CLI

# GitHub Repository Analyzer (RC3 AI Hackathon, Task 4, Track B)

`python analyze.py <github-repo-url>` prints a terminal report with five sections:

1. **Tech Stack**: each item comes with its evidence (languages API, manifest line, or file that is present)
2. **File Structure**: file and directory counts, max depth, size, top-level entries, top extensions, key files
3. **Code Complexity**: a 0-100 score, with the formula and every component printed
4. **Dependency Health**: each dependency's pinned/latest/state, plus the definition of "healthy"
5. **Contribution Activity**: a terminal bar chart of commits per week (last 12 weeks) and the top contributors

The tool never invents data. Anything it cannot determine is printed as `Not available: <reason>`.

## Libraries

- Python 3.12
- [`requests`](https://pypi.org/project/requests/): HTTP calls
- [`rich`](https://pypi.org/project/rich/): terminal panels, tables, colours
- Standard library only for the rest (`argparse`, `json`, `re`, `math`, `base64`, `datetime`, `os`, `urllib.parse`, `time`)

There are no other dependencies (no `python-dotenv`; the `.env` file is read by a small stdlib loader in `analyzer/envfile.py`).

APIs used: the GitHub REST API, PyPI JSON (`https://pypi.org/pypi/{name}/json`) and the npm registry
(`https://registry.npmjs.org/{name}/latest`). The GitHub token is **only** sent to api.github.com.

## Install (PowerShell)

```powershell
cd C:\Users\umara\Downloads\RC3_AI_HACK\task4
python -m pip install -r requirements.txt      # or: pip install requests rich
```

## Run (PowerShell)

```powershell
python analyze.py https://github.com/psf/requests
python analyze.py github.com/expressjs/express.git/
python analyze.py https://github.com/octocat/Hello-World --save demo/hello_world.txt
python analyze.py help        # usage guide, token status, exit codes
"exit=$LASTEXITCODE"
```

Accepted URL forms: `https://github.com/o/r`, `http://...`, a trailing `/`, a `.git` suffix,
`/tree/<branch>/...`, and no scheme (`github.com/o/r`).

Options:
- `--save PATH`: also write the rendered report as plain text to `PATH` (for example `demo/psf_requests.txt`).

If you redirect output to a file with `*>`, first run `$env:PYTHONUTF8 = "1"` so the bar characters encode correctly.

## Setting GITHUB_TOKEN

The token is **optional**. Without it GitHub allows 60 requests/hour per IP (about 5 analyses).
With it you get 5,000 requests/hour. The token is read only from the environment (or the `.env` file below).
It is never hard-coded, never printed and never sent to PyPI or npm.

### 1. Create a token

Go to <https://github.com/settings/tokens>.

- **Fine-grained token (recommended):** "Generate new token" -> Repository access: **Public repositories (read-only)**.
  No extra permissions are needed. Pick a short expiry.
- **Classic token:** "Generate new token (classic)" -> leave **every scope unticked**. Public data needs no scopes.

Copy the token (`github_pat_...` or `ghp_...`). GitHub shows it only once.

### 2. Make it available (pick ONE option)

**Option 1: `.env` file (auto-loaded)**

```powershell
Copy-Item .env.example .env
notepad .env          # set: GITHUB_TOKEN=ghp_yourtokenhere
```

`analyze.py` reads `task4/.env` at startup (via `analyzer/envfile.py`, stdlib only). Blank lines and `#` comments
are ignored, and optional quotes around the value are stripped. **A variable already set in your environment wins**:
the `.env` value never overrides an existing `$env:GITHUB_TOKEN`. `.env` is listed in `.gitignore`; never commit it.

**Option 2: current PowerShell session only**

```powershell
$env:GITHUB_TOKEN = "ghp_yourtokenhere"
```

This lasts until you close the terminal.

**Option 3: permanent for your Windows user**

```powershell
setx GITHUB_TOKEN "ghp_yourtokenhere"
```

`setx` only affects **new** terminals. Close and reopen PowerShell before running the analyzer.

### 3. Check that it is picked up

Run any analysis and look at the report:
- The header shows `Authenticated yes`.
- The footer shows `token used: yes (authenticated, 5,000 requests/hour)` and
  `rate limit remaining: NNNN/5000`. Without a token you would see `/60`.

You can also check your quota directly (the token is not printed):

```powershell
Invoke-RestMethod https://api.github.com/rate_limit -Headers @{ Authorization = "Bearer $env:GITHUB_TOKEN" } | Select-Object -ExpandProperty rate
```

### 4. Remove it

```powershell
Remove-Item Env:GITHUB_TOKEN                 # current session
[Environment]::SetEnvironmentVariable("GITHUB_TOKEN", $null, "User")   # undo setx (new terminals)
Remove-Item .env                             # if you used option 1
```

If GitHub rejects the token (401), the tool exits with code 5 and tells you to fix or remove it.

## What each section means

### 1. Tech Stack
- **Languages**: from the GitHub languages API (Linguist byte counts). Only languages with at least 1% of bytes are listed,
  e.g. `GitHub languages API: 92.1% of bytes`.
- **Frameworks / libraries**: read from `requirements.txt` / `package.json` at the repo root; if a kind is missing at the root,
  the 2 shallowest copies in sub-folders are used (e.g. `frontend/package.json`). Evidence names the file and line.
  Packages found only in `devDependencies` are labelled `dev tool`.
- **Build files and tools**: presence only (e.g. `pyproject.toml`, `go.mod`, `Dockerfile`, `.github/workflows/*.yml`),
  evidence `file present: <path>`.
- Nothing is guessed from the repository name or description.

### 2. File Structure
From one recursive Git tree call: files (blobs), directories, max depth (`path.count("/")`, a root file = 0), total size,
top-level entries with the number of files beneath each directory and a **purpose** note, the top 8 extensions, and key
files (README, LICENSE, tests/, docs/, CI workflows, Dockerfile). Purpose notes come only from a fixed list of well-known
names (`src/` source code, `tests/` tests, `.github/` CI workflows, `frontend/` frontend app, ...). Unknown names show `-`
instead of a guess.

### 3. Code Complexity (0-100)
Four components, each worth up to 25 points:

| Component | Formula | Full 25 points when |
|---|---|---|
| Size | `25 * min(1, log10(max(files,1)) / 4)` | 10,000+ files |
| Depth | `25 * min(1, max_depth / 10)` | depth 10+ |
| Large files | `25 * min(1, (share of files > 100 KB) / 0.10)` | 10%+ of files over 100 KB |
| Language spread | `25 * min(1, (languages with >= 1% of bytes - 1) / 5)`, floor 0 | 6+ languages |

Bands: `< 25` Low, `25 <= s < 50` Moderate, `50 <= s < 75` High, `>= 75` Very high.

Worked example: 1,200 files, depth 6, 18 files > 100 KB, 3 languages >= 1%
-> 19.24 + 15.00 + 3.75 + 10.00 = **48.0 (Moderate)**.

Caveat (printed in the report): this is a heuristic based on file count, nesting, file sizes and language bytes from
the GitHub API. It does **not** measure lines of code or cyclomatic complexity.

### 4. Dependency Health
- **Pinned** = exact version: `pkg==1.2.3` for pip, bare `1.2.3` for npm (no `^ ~ > < * x` or ranges).
- **Up-to-date** = pinned version equals the registry's latest (PyPI `info.version`, npm `latest` dist-tag).
- States: `up-to-date`, `outdated`, `unknown (range)`, `unknown (lookup failed)`, `unknown (unparsable)`.
- **Healthy = at least 80% of dependencies pinned to an exact version AND at least 80% of pinned dependencies on the
  latest release.** 0 dependencies -> "Not applicable"; 0 pinned -> Not healthy.

### 5. Contribution Activity
- Commits per week on the default branch for the last 12 weeks, drawn as a 40-character bar chart; totals cover 52 weeks.
- Top 5 contributors by **all-time** commit count (GitHub contributors API, cached by GitHub).
- A repo with no recent commits still shows the chart plus "No commits in the last 52 weeks", or "No commits in the last
  12 weeks shown (N earlier in the 52-week window)" when the commits are older.

## Error messages and exit codes

| Exit | Condition | Message (example) |
|---|---|---|
| 0 | Success (some sections may still be `Not available: <reason>`) | the report |
| 1 | Unexpected error | `Unexpected error: <msg>` |
| 2 | Invalid URL (or missing argument) | `Invalid URL: 'not-a-url' is not a GitHub repository URL. Expected e.g. https://github.com/owner/repo` |
| 3 | Repository not found or private | `Repository not found: x/doesnotexist (check spelling, or it may be private)` |
| 4 | GitHub rate limit | `GitHub API rate limit exceeded (60/hour). Resets at HH:MM UTC ... Set GITHUB_TOKEN ...` |
| 5 | Bad token (401) | `GITHUB_TOKEN was rejected by GitHub (401 Bad credentials). Fix it or remove it (Remove-Item Env:GITHUB_TOKEN, or edit the GITHUB_TOKEN line in .env)` |
| 6 | Network error | `Network error: could not reach api.github.com (<ExceptionName>). Check your internet connection.` |

Section-level problems do not stop the report. Examples: `Not available: Repository is empty`,
`Not available: No requirements.txt or package.json found (repo root or sub-folders)`,
`Not available: GitHub is still computing statistics, try again in a minute`,
`Not available: GitHub rate limit reached (resets HH:MM UTC)`.
The report ends with a list of every unavailable section and its reason, and a footer with the number of GitHub
calls, rate limit remaining, and whether a token was used.

## Testing

```powershell
python -m unittest -v tests.test_offline
```
Ten offline tests with mocked GitHub responses cover URL parsing, the rate limit (exit 4), repo not found (3), bad token
(5), network error (6), invalid URL (2), stats still computing (HTTP 202 -> "Not available"), no manifest, a manifest in a
sub-folder, and a failed registry lookup (shown as `unknown (lookup failed)`, never as up to date).
Live runs on four public repositories are saved in `demo/`.

## How the tool avoids assumptions

- Every value comes from the GitHub, PyPI or npm APIs at run time. When a call fails or returns nothing, that section
  prints `Not available: <reason>` and the rest of the report still runs.
- Evidence is printed next to each tech-stack item, and the complexity formula, the "healthy" definition and the
  folder-purpose rule are printed in the report itself.
- Version ranges are never judged up to date or outdated, and failed lookups are left out of the percentages.

## Known limitations

1. Only `requirements.txt` and `package.json` are parsed: at the repo root, or the 2 shallowest of each kind in sub-folders
   when the root has none (`node_modules/`, `vendor/`, `venv/`, `dist/`, `build/` skipped). `pyproject.toml`, `setup.py`,
   `Pipfile`, lock files, `go.mod` and nested `-r` files are detected but not parsed.
2. The complexity score is a **structural proxy** (file count, depth, file sizes, language bytes), not lines of code or static analysis.
3. Language percentages are GitHub Linguist **bytes** (vendored/generated files excluded by Linguist rules).
4. Very large repos: GitHub truncates the tree above 100,000 entries / 7 MB, so structure and complexity become lower bounds and are flagged.
5. Commit statistics are computed by GitHub in the background. The first request can return 202; the tool retries
   5 times (about 15 s) and then reports "Not available". Run again a minute later.
6. Contributor counts are all-time, cached by GitHub, and exclude anonymous contributors.
7. Dependency health: unpinned ranges cannot be judged up to date (`unknown (range)`); at most **30** registry lookups
   per run (pinned first); `peerDependencies` / `optionalDependencies` ignored; simplified version comparison.
8. Without `GITHUB_TOKEN`: 60 requests/hour per IP. Private repositories are reported as "not found".
9. Files over 1 MB cannot be read through the contents API.
10. Every number comes from the GitHub, PyPI or npm APIs at run time. Nothing is estimated or filled in.

## Demo evidence (`demo/`)

| File | Command |
|---|---|
| `demo/psf_requests.txt` | `python analyze.py https://github.com/psf/requests --save demo/psf_requests.txt` |
| `demo/expressjs_express.txt` | `python analyze.py https://github.com/expressjs/express --save demo/expressjs_express.txt` |
| `demo/hello_world.txt` | `python analyze.py https://github.com/octocat/Hello-World --save demo/hello_world.txt` |
| `demo/unmapped_mit_hackathon.txt` | `python analyze.py https://github.com/umarahad2005/unmapped_mit_hackathon --save demo/unmapped_mit_hackathon.txt` (manifests in sub-folders) |
| `demo/failures.txt` | live runs: invalid URL (exit 2), not found (exit 3), bad token (exit 5) |
| `demo/rate_limit_simulated.txt` | rate limit (exit 4), **simulated** with a mocked 403 response; the live limit was never exhausted |
| `demo/tests_offline.txt` | output of `python -m unittest -v tests.test_offline` (10 offline tests) |

```powershell
New-Item -ItemType Directory -Force demo | Out-Null
$env:PYTHONUTF8 = "1"
& {
  python analyze.py not-a-url ; "exit=$LASTEXITCODE"
  python analyze.py https://github.com/x/doesnotexist ; "exit=$LASTEXITCODE"
  $t=$env:GITHUB_TOKEN; $env:GITHUB_TOKEN="bad"; python analyze.py https://github.com/psf/requests; "exit=$LASTEXITCODE"; $env:GITHUB_TOKEN=$t
  python analyze.py https://github.com/octocat/Hello-World ; "exit=$LASTEXITCODE"
} *> demo/failures.txt
```

## Project layout

```
task4/
  analyze.py                 CLI: argparse, .env loading, exit codes, --save
  analyzer/envfile.py        load_env_file(path): stdlib .env loader (existing env wins)
  analyzer/github_client.py  parse_repo_url, GitHubClient.get, error classes
  analyzer/fetch.py          fetch_bundle(): every GitHub call once
  analyzer/techstack.py      detect_stack(bundle)
  analyzer/structure.py      summarize_structure(bundle)
  analyzer/complexity.py     score_complexity(bundle)
  analyzer/deps.py           analyze_deps(bundle)  (PyPI / npm lookups, no token sent)
  analyzer/activity.py       analyze_activity(bundle)
  analyzer/report.py         render(...)  (rich output only)
  .env.example               template for .env
  requirements.txt           requests, rich
  analyzer/help.py           `python analyze.py help` guide
  tests/test_offline.py      10 offline tests with mocked GitHub responses (no network, no token)
  demo/                      saved reports
  plan/                      SPEC.md, STAGE_PROMPTS.md
```
