# SPEC: GitHub Repository Analyzer CLI (Task 4, Track B)

The code must satisfy this spec. Build stage by stage; each module only has to meet its own contract below.
If this file and STAGE_PROMPTS.md disagree, STAGE_PROMPTS.md wins on names and shapes; SPEC is reference for edge cases.

**TL;DR (read this, consult the rest only when a stage test fails)**
- **Exit codes:** 0 ok, 1 unexpected, 2 invalid URL, 3 not found, 4 rate limit, 5 bad token (401), 6 network.
- **Errors:** `AnalyzerError` > `InvalidRepoURL`, `RepoNotFound` (gate 404 only), `RateLimitError(reset_epoch)`, `AuthError`, `NetworkError`. `get(path, params=None) -> requests.Response`, timeout=15.
- **Bundle keys (flat):** `repo`, `languages`, `languages_error`, `tree`, `tree_truncated`, `tree_error`, `files`, `commit_activity`, `activity_error`, `contributors`, `contributors_error`.
- **Complexity:** 4 x 25 = size `25*min(1,log10(files)/4)` + depth `25*min(1,max_depth/10)` + large `25*min(1,share>100KB/0.10)` + spread `25*min(1,(langs>=1% - 1)/5)`. Bands half-open: <25 Low, 25<=s<50 Moderate, 50<=s<75 High, >=75 Very high. Bytes/file counts, not LOC.
- **Healthy:** >=80% of deps pinned (exact) AND >=80% of pinned deps == registry latest. 0 deps -> `healthy None` ("Not applicable"); 0 pinned -> `healthy False`.
- Sections 6.2-9 are reference only; consult when a stage test fails. Section 7 (layout, `--ascii`, footer) is optional.

- **Run:** `python analyze.py <github-repo-url> [--save report.txt]` (`--ascii` is optional, cut first)
- **Runtime:** Python 3.12, `requests`, `rich`, and the stdlib. Nothing else, so no `packaging`, `PyGithub` or `click`.
- **Network:** calls only `api.github.com`, `pypi.org/pypi/{name}/json` and `registry.npmjs.org/{name}/latest`.
- **Golden rule:** never invent data. If a value is missing, show `Not available: <reason>`.

Legend: **[V]** means checked against docs.github.com (or a live registry call) on 2026-11-05. **[U]** means not verified (see section 9).

---

## 1. Module layout and responsibilities

```
task4/
  analyze.py              CLI entry: argparse, wiring, exit codes, prints report
  analyzer/__init__.py    empty
  analyzer/github_client.py  parse_repo_url, GitHubClient, error classes, token from env
  analyzer/fetch.py       fetch_bundle(): every GitHub call happens here, once
  analyzer/techstack.py   detect_stack(bundle)        pure
  analyzer/structure.py   summarize_structure(bundle) pure
  analyzer/complexity.py  score_complexity(bundle)    pure
  analyzer/deps.py        analyze_deps(bundle, session=None)  parsing is pure; registry calls isolated
  analyzer/activity.py    analyze_activity(bundle)    pure
  analyzer/report.py      render(console, repo_meta, sections, token_used) - presentation only, no logic, no network
  README.md               Track B, libraries, how to run (PowerShell), definitions, limitations
  demo/                   saved outputs of 3 demo runs (requests, express, Hello-World) via Console(record=True).save_text
```

Rules:
- Only `github_client`, `fetch` and `deps` (registry lookups only) do network I/O. All other modules are pure functions of the `bundle` dict, so they can be tested offline with a hand-made bundle.
- Every section function returns a dict with **at least** `{"status": "ok" | "unavailable", "reason": str | None}`. When `status == "unavailable"`, `reason` is a short human sentence and the other keys may be missing. When `status == "ok"`, `reason` is `None` and an optional `"notes": [str]` holds caveats such as "tree truncated".
- `report.py` never computes numbers. It only formats what the sections return.

---

## 2. Endpoints

Common request settings (all GitHub calls go through `GitHubClient.get`):

| Item | Value |
|---|---|
| Base URL | `https://api.github.com` |
| Headers | `Accept: application/vnd.github+json`, `X-GitHub-Api-Version: 2022-11-28`, `User-Agent: rc3-repo-analyzer` |
| Auth | Only if `GITHUB_TOKEN` env var is non-empty: `Authorization: Bearer <token>`. Never hard-coded, logged or printed. |
| Timeout | `timeout=15` seconds |
| Session | one `requests.Session` per run |
| Rate info | After every response, store `x-ratelimit-remaining`, `x-ratelimit-limit` and `x-ratelimit-reset` on the client (`client.rate`) **[V]** |

### Per-section endpoints

| # | Used by | Method + path | Params | Success | Edge cases -> handling |
|---|---|---|---|---|---|
| 1 | all (gate) | `GET /repos/{o}/{r}` | none | 200: `default_branch`, `full_name`, `description`, `stargazers_count`, `forks_count`, `archived`, `size`, `html_url` | 404 -> `RepoNotFound` (**fatal**). 401 -> `AuthError` (fatal). Private repos without a token also return 404, so the message says "not found or private". 301 for a renamed repo is followed automatically by requests. |
| 2 | techstack, complexity | `GET /repos/{o}/{r}/languages` | none | 200: `{"Python": 812345, ...}` bytes per language **[V]** | `{}` (no recognised code) -> languages unavailable: "GitHub detected no languages". |
| 3 | structure, complexity, techstack | `GET /repos/{o}/{r}/git/trees/{branch}` | `recursive=1` | 200: `{"tree":[{"path","mode","type":"blob"/"tree"/"commit","sha","size"(blobs only)}], "truncated": bool}` **[V]** | `truncated=true` (over 100,000 entries or 7 MB) **[V]** -> keep the partial tree and add the note "tree truncated by GitHub, counts are a lower bound". 409 -> "Repository is empty" **[U: docs only say 409 Conflict]**. 404 -> "default branch tree not found". `{branch}` is URL-encoded with `quote(branch, safe="")` **[U for branch names containing "/"]**. Entries with `type == "commit"` are submodules: count them separately and never treat them as files. |
| 4 | deps, techstack | `GET /repos/{o}/{r}/contents/{path}` | `ref={default_branch}` | 200: `{"encoding":"base64","content":"...","size":N}` | Fetch only `requirements.txt` and `package.json` at the **repo root**, and only if they appear in the tree (if the tree is unavailable, try both and read 404 as absent). `encoding == "none"` or empty content (file over 1 MB **[V]**) -> "file larger than 1 MB, not parsed". Decode with `base64.b64decode(content).decode("utf-8", "replace")`. |
| 5 | activity | `GET /repos/{o}/{r}/stats/commit_activity` | none | 200: list of 52 `{"week": epoch_sunday, "total": int, "days": [7 ints]}` **[V]** | 202 = statistics still being computed **[V]**: retry up to 5 times, sleeping 1, 2, 3, 4, 5 s (15 s max). If still 202 -> "GitHub is still computing commit statistics, try again in a minute". 204 -> "no commit statistics (empty repo)" **[V: 204 documented]**. |
| 6 | activity | `GET /repos/{o}/{r}/contributors` | `per_page=10` | 200: list of `{"login","contributions",...}`, sorted by commit count descending **[V]** | 204 -> "no contributors (empty repo)" **[V]**. 403 with no rate-limit signal -> "contributor list too large for GitHub to compute" **[U: wording]**. Data may be a few hours stale (cached) **[V]**. |

**Call budget per run:** at most 1+1+1+2+6+1 (+1 branch fallback) = **13 GitHub calls**, typically 5-7. Without a token the limit is 60 calls/hour per IP **[V]**, which is about 4-5 runs/hour. With a token it is 5,000/hour **[V]**.

### Registry endpoints (deps.py only)

| Registry | URL | Field used | Edge cases |
|---|---|---|---|
| PyPI | `https://pypi.org/pypi/{normalized_name}/json` | `info.version` | 404 -> "not found on PyPI". Timeout or 5xx -> "registry error". |
| npm | `https://registry.npmjs.org/{name}/latest` (scoped names: `@scope%2Fname`, **[V]**: `@types%2Fnode` returns 200) | `version` | 404 -> "not found on npm". |

Registry calls use a **separate** session or plain `requests.get` with `timeout=(5, 10)`, `User-Agent: rc3-repo-analyzer`, and **no GitHub Authorization header** so the token never leaks to third parties. Cache results per name within a run.

---

## 3. Function contracts

### 3.1 `analyzer/github_client.py`

```python
class AnalyzerError(Exception):          exit_code = 1
class InvalidRepoURL(AnalyzerError):     exit_code = 2
class RepoNotFound(AnalyzerError):       exit_code = 3   # 404 on GET /repos/{o}/{r} only
class RateLimitError(AnalyzerError):     exit_code = 4   # .reset_epoch: int|None, .retry_after: int|None; message shows HH:MM UTC
class AuthError(AnalyzerError):          exit_code = 5
class NetworkError(AnalyzerError):       exit_code = 6
# Any other non-2xx/409 status (incl. 404 on tree/contents) -> plain AnalyzerError with .status and GitHub's "message"

def parse_repo_url(url: str) -> tuple[str, str]: ...
```

`parse_repo_url` accepts:
- `https://github.com/o/r`, `http://...`, `github.com/o/r` (no scheme), `www.github.com/o/r`
- a trailing `/`, a trailing `.git`
- extra path such as `/tree/main/src`, `/blob/...`, `/issues`; query strings and `#fragment` are stripped
- surrounding whitespace and quotes

Algorithm:
1. Strip whitespace and quotes.
2. If there is no `://`, prepend `https://`.
3. Run `urllib.parse.urlsplit`.
4. The host (lowercased, `www.` removed) must equal `github.com`.
5. Take the first 2 path segments. Fewer than 2 means invalid.
6. Strip `.git` from the repo segment.
7. Validate: owner `^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$`, repo `^[A-Za-z0-9._-]{1,100}$` and not `.` or `..`.

Examples:
- `parse_repo_url("github.com/psf/requests.git/") -> ("psf", "requests")`
- `parse_repo_url("not-a-url")` -> `InvalidRepoURL("'not-a-url' is not a GitHub repository URL. Expected e.g. https://github.com/owner/repo")`

```python
class GitHubClient:
    def __init__(self, token: str | None = None): ...   # token = os.environ.get("GITHUB_TOKEN","").strip() or None (read in analyze.py or here)
    rate: dict        # {"remaining": int|None, "limit": int|None, "reset_epoch": int|None}
    calls: int        # number of HTTP requests made
    def get(self, path: str, params: dict | None = None) -> requests.Response: ...
    # returns 2xx/409 as-is, raises otherwise; timeout=15
```

Raise order for anything that is not 2xx/409:
1. `requests.Timeout` / `ConnectionError` -> `NetworkError`.
2. 401 -> `AuthError`.
3. 403 or 429 with `x-ratelimit-remaining == "0"` -> `RateLimitError(reset_epoch=int(x-ratelimit-reset))` **[V]**.
4. 403 or 429 with a `retry-after` header, or a message containing "secondary rate limit" -> `RateLimitError(retry_after=int or 60)` **[V]**.
5. 404 on the gate path `/repos/{o}/{r}` -> `RepoNotFound`.
6. Anything else (including 404 on tree/contents) -> `AnalyzerError` with `.status` and GitHub's `message`.

### 3.2 `analyzer/fetch.py`

```python
def fetch_bundle(client: GitHubClient, owner: str, repo: str) -> dict: ...
```

Flat keys (same as STAGE_PROMPTS Stage 2). Only the `/repos` gate call may raise: `RepoNotFound`, `AuthError`, `RateLimitError`, `NetworkError`.

Every later call is wrapped in `try/except AnalyzerError`, storing `str(e)` in the matching `*_error` key. After the first `RateLimitError`, no further GitHub calls are made, and every remaining `*_error` is `"GitHub rate limit reached (resets HH:MM UTC)"`. 204 -> data `None`, error `"no data (empty repo)"`.

```json
{
  "repo": {"full_name": "psf/requests", "description": "...", "default_branch": "main", "stargazers_count": 52000, "...": "raw /repos JSON"},
  "languages": {"Python": 812345, "Makefile": 1200},
  "languages_error": null,
  "tree": [{"path": "src/requests/api.py", "type": "blob", "size": 6449}, {"path": "src", "type": "tree"}],
  "tree_truncated": false,
  "tree_error": null,
  "files": {"requirements.txt": "requests==2.32.0\n..."},
  "commit_activity": [{"week": 1730592000, "total": 4, "days": [0,1,0,2,1,0,0]}],
  "activity_error": null,
  "contributors": [{"login": "kennethreitz", "contributions": 3100}],
  "contributors_error": null
}
```

- `files` holds only root `requirements.txt` / `package.json` that exist in the tree (missing file = missing key).
- Unavailable example: `"tree": null, "tree_error": "Repository is empty (GitHub returned 409)"`.
- The rate snapshot and call count stay on `client` (optional footer, section 7).

### 3.3 `analyzer/techstack.py`

```python
def detect_stack(bundle: dict) -> dict: ...
```

Detection rules (each item must carry its evidence string):

| Category | Source | Rule | Evidence format |
|---|---|---|---|
| language | `/languages` | each language with 1% or more of bytes | `"GitHub languages API: 92.4% of code bytes"` |
| framework | `bundle["files"]["package.json"]` deps | name in a known map: react, next, vue, @angular/core, svelte, express, koa, fastify, @nestjs/core, jest, mocha, vitest, typescript, webpack, vite, eslint | `"package.json dependencies: express ^4.19.2"` |
| framework | `bundle["files"]["requirements.txt"]` | django, flask, fastapi, numpy, pandas, torch, tensorflow, scikit-learn, pytest, sqlalchemy, requests | `"requirements.txt line 3: Django==4.2.7"` |
| build (presence only, never read) | tree (root files) | `pyproject.toml`, `setup.py`, `setup.cfg`, `Pipfile`, `poetry.lock`, `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`, `go.mod`, `Cargo.toml`, `pom.xml`, `build.gradle`, `Gemfile`, `composer.json`, `Makefile`, `CMakeLists.txt` | `"file present: pyproject.toml"` |
| tool (incl. CI) | tree | `Dockerfile` / `docker-compose.yml` -> Docker; `.github/workflows/*.yml` -> GitHub Actions (count them); `.travis.yml`, `.gitlab-ci.yml`, `tox.ini`, `.pre-commit-config.yaml` | `"3 workflow files in .github/workflows/"` |

Output:

```json
{"status": "ok", "reason": null,
 "items": [
   {"name": "Python", "category": "language", "evidence": "GitHub languages API: 98.1% of code bytes"},
   {"name": "tox", "category": "tool", "evidence": "file present: tox.ini"},
   {"name": "GitHub Actions", "category": "tool", "evidence": "5 workflow files in .github/workflows/"}],
 "notes": ["Frameworks are detected only from root requirements.txt/package.json and known file names."]}
```

Categories are `language` | `framework` | `tool` | `build` (prompt names).

- **Unavailable:** if items is empty after all rules: status "unavailable", reason "No languages or known manifest/tooling files detected" (e.g. Hello-World).
- **Partial data:** if only some sources failed, keep `status: "ok"` and add a note such as "language data unavailable: <reason>".
- **Never** guess a framework from the repo name or description.

### 3.4 `analyzer/structure.py`

```python
def summarize_structure(bundle: dict) -> dict: ...
```

Definitions:
- **File** = tree entry with `type == "blob"`.
- **Directory** = entry with `type == "tree"`.
- **Depth of a file** = `path.count("/")`, so a root file has depth 0 and `a/b/c.py` has depth 2.
- **Extension** = text after the last `.` of the basename, lowercased. Use `(none)` if there is no dot and `(dotfile)` if the name starts with a dot and has no other dot.

```json
{"status": "ok", "reason": null,
 "total_files": 312, "total_dirs": 41, "max_depth": 5, "total_size_bytes": 4821331,
 "top_level": [{"name": "src", "type": "dir", "files": 120}, {"name": "tests", "type": "dir", "files": 80}, {"name": "README.md", "type": "file", "files": 1}],
 "top_extensions": [{"ext": "py", "count": 210}, {"ext": "md", "count": 30}],
 "notable": ["README.md", "LICENSE", "tests/", "docs/", ".github/workflows"],
 "truncated": false,
 "note": null}
```

- Optional, not in the prompt: `submodules`, `avg_depth`, `largest_files` (top 5), `pct` per extension.
- `top_level` lists at most 15 entries (dirs first by file count, then files) plus `"+N more"`.
- `top_extensions` holds the top 8.
- **Unavailable:** `{"status": "unavailable", "reason": "Repository is empty (GitHub returned 409)"}`, or the tree's own reason. If there are 0 blobs: `"Repository has no files on the default branch"`.

### 3.5 `analyzer/complexity.py`

```python
def score_complexity(bundle: dict) -> dict: ...   # formula in section 5
```

```json
{"status": "ok", "reason": null,
 "score": 48.0, "band": "Moderate",
 "components": [
   {"name": "size",            "value": "1,200 files",            "points": 19.24, "max": 25},
   {"name": "depth",           "value": "max depth 6",            "points": 15.0,  "max": 25},
   {"name": "large_files",     "value": "18 of 1,200 files >100 KB (1.5%)", "points": 3.75, "max": 25},
   {"name": "language_spread", "value": "3 languages >=1%",       "points": 10.0,  "max": 25}],
 "formula": "size 25*min(1,log10(files)/4) + depth 25*min(1,max_depth/10) + large 25*min(1,share>100KB/0.10) + spread 25*min(1,(langs>=1% - 1)/5)",
 "caveat": "Heuristic based on file count, nesting, file sizes and language bytes from the GitHub API; it does not measure lines of code or cyclomatic complexity."}
```

- **Unavailable:** if the tree is unavailable or has 0 blobs: `{"status": "unavailable", "reason": "Needs the file tree: <tree reason>"}`.
- **Languages unavailable/empty:** spread = 0 and add the note "language data unavailable". No rescaling.

### 3.6 `analyzer/deps.py`

```python
def parse_requirements(text: str) -> list[dict]: ...      # pure
def parse_package_json(text: str) -> list[dict]: ...      # pure
def classify_spec(ecosystem: str, spec: str) -> str: ...  # "pinned" | "range" | "unknown"
def compare_versions(a: str, b: str) -> int | None: ...   # -1/0/1, None if unparsable
def analyze_deps(bundle: dict, lookup=None, cap: int = 30) -> dict: ...  # lookup(ecosystem, name) -> (latest|None, reason|None); default does HTTP
```

Each parsed dependency looks like `{"ecosystem": "pypi"|"npm", "name": str, "spec": str, "pinned": bool, "source": "requirements.txt line 4"}`. Manifest text comes from `bundle["files"]`.

Output (prompt shape):

```json
{"status": "ok", "reason": null,
 "manifests": ["package.json"],
 "deps": [
   {"name": "body-parser", "ecosystem": "npm", "spec": "^2.2.0", "pinned": false, "latest": "2.2.0", "state": "unknown (range)"},
   {"name": "debug", "ecosystem": "npm", "spec": "4.4.0", "pinned": true, "latest": "4.4.3", "state": "outdated"},
   {"name": "foo", "ecosystem": "npm", "spec": "git+https://...", "pinned": false, "latest": null, "state": "unknown (unparsable)"}],
 "pinned_pct": 3.6, "uptodate_pct_of_pinned": 0.0, "healthy": false,
 "definition": "Healthy = at least 80% of dependencies pinned to an exact version AND at least 80% of pinned dependencies on the latest release.",
 "note": "Checked 28 of 28."}
```

`state` takes exactly one of: `up-to-date`, `outdated`, `unknown (range)`, `unknown (lookup failed)`, `unknown (unparsable)`. Optional extra in `note`: "major/minor/patch behind" via `compare_versions`.

Unavailable / edge cases:
- No manifest at the root: `{"status": "unavailable", "reason": "No requirements.txt or package.json found at repo root"}` (optionally append other manifests seen, e.g. "found: pyproject.toml - not parsed").
- Manifest present but 0 deps: `status "ok"`, `healthy None`, note "Not applicable: manifest declares no dependencies".
- 0 pinned deps: `healthy False`, note "no pinned dependencies".
- `package.json` is invalid JSON: unavailable for that manifest with the reason `"package.json is not valid JSON: <err>"`.

### 3.7 `analyzer/activity.py`

```python
def analyze_activity(bundle: dict) -> dict: ...
```

```json
{"status": "ok", "reason": null,
 "weeks": [{"week_start": "2026-08-16", "commits": 7}],
 "total_52w": 143, "active_weeks_52w": 31,
 "top_contributors": [{"login": "nateprewitt", "commits": 802}],
 "contributors_reason": null,
 "note": null}
```

- `week_start` = `datetime.fromtimestamp(week, timezone.utc).date().isoformat()` (a Sunday).
- `weeks` = the last 12 weeks (charted); `total_52w` / `active_weeks_52w` use all 52. `top_contributors` = top 5.
- Contributor counts are all-time default-branch commits (GitHub API, cached); label them that way.
- **Inactive repo** (all totals 0, e.g. octocat/Hello-World): `status: "ok"`, `total_52w: 0`, the chart (zero bars) is still shown plus the note "No commits in the last 52 weeks".
- **Weekly part unavailable:** weekly shows `Not available: <activity_error>`, contributors still shown. The section is unavailable only if both parts fail.

### 3.8 `analyzer/report.py` and `analyze.py`

```python
def render(console: rich.console.Console, repo_meta: dict, sections: dict, token_used: bool) -> None: ...
# repo_meta = bundle["repo"]; sections = {"techstack": ..., "structure": ..., "complexity": ..., "deps": ..., "activity": ...}
# optional / cut first: --ascii flag and a rate-limit footer (would need extra args)

def main(argv: list[str] | None = None) -> int: ...   # analyze.py; sys.exit(main())
```

`main` flow:
1. `if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8")` (redirect-safe on Windows), then parse args.
2. `parse_repo_url`.
3. Create `GitHubClient(token)`.
4. Run `fetch_bundle` with a `console.status("Fetching...")` spinner.
5. Run the 5 section functions. Wrap each in `try/except Exception as e` so it becomes `{"status": "unavailable", "reason": f"internal error: {e}"}`; one bug must not kill the whole report.
6. `render`.
7. If `--save`, `console.save_text(path)`.
8. Return 0.

Catch `AnalyzerError` and print a red Panel with the message, then return `e.exit_code`. Catch `KeyboardInterrupt` and return 130. Use `Console(record=True)` always, which is cheap.

---

## 4. Error handling

| Condition | Detected by | User-facing message (exact) | Exit |
|---|---|---|---|
| Missing argument | argparse | argparse usage text | 2 |
| Invalid URL | `parse_repo_url` | `Invalid URL: '<input>' is not a GitHub repository URL. Expected e.g. https://github.com/owner/repo` | 2 |
| Repo not found or private | gate `GET /repos/o/r` -> 404 | `Repository not found: github.com/<o>/<r> does not exist or is private. Check the spelling.` | 3 |
| Primary rate limit | 403/429 and `x-ratelimit-remaining: 0` | `GitHub API rate limit exceeded (<limit>/hour). Resets at <HH:MM> UTC (in <N> min). Set GITHUB_TOKEN to get 5,000 requests/hour: $env:GITHUB_TOKEN = "<your token>"` | 4 |
| Secondary rate limit | 403/429 and `retry-after` header or "secondary rate limit" in message | `GitHub secondary rate limit hit. Wait <retry-after or 60> seconds and try again.` | 4 |
| Bad token | 401 on any call | `GITHUB_TOKEN was rejected by GitHub (401 Bad credentials). Fix it or remove it: Remove-Item Env:GITHUB_TOKEN` | 5 |
| Network / DNS / timeout | `requests.ConnectionError` / `Timeout` on the gate call | `Network error: could not reach api.github.com (<ExceptionName>). Check your internet connection.` | 6 |
| Rate limit / network **after** the gate | fetch per-item try/except | the section shows `Not available: GitHub rate limit reached (resets at HH:MM UTC)` | 0 |
| Empty repository | tree 409 | structure/complexity: `Not available: Repository is empty (GitHub returned 409)` | 0 |
| No manifest | file absent in tree root | deps: `Not available: No requirements.txt or package.json at the repository root` | 0 |
| Stats still computing | 202 after 5 retries | activity chart: `Not available: GitHub is still computing commit statistics; try again in a minute` | 0 |
| Manifest larger than 1 MB | contents `encoding == "none"` | deps: `Not available: <file> is larger than 1 MB and was not parsed` | 0 |
| Registry down / 404 | deps lookup | per row: `unknown (lookup failed)` | 0 |
| Unexpected exception in a section | `main` try/except | section: `Not available: internal error: <msg>` | 0 |
| Unexpected exception elsewhere | top-level except | `Unexpected error: <msg>` | 1 |

Rules:
- The token is never echoed.
- Messages for PowerShell users show PowerShell syntax (`$env:X = ...`, `Remove-Item Env:X`).
- Reset time comes from `x-ratelimit-reset` (epoch seconds, UTC) **[V]**.

---

## 5. Complexity score (0-100)

The score has four components, each worth up to 25 points. `clamp1(x) = min(1, max(0, x))`.

| Component | Formula | Hits 25 when |
|---|---|---|
| Size | `25 * clamp1(log10(files) / 4)` | 10,000 or more files |
| Depth | `25 * clamp1(max_depth / 10)` | max folder depth of 10 or more |
| Large files | `25 * clamp1(share_large / 0.10)`, where `share_large = blobs with size > 102,400 B / files` | 10% or more of files are over 100 KB |
| Language spread | `25 * clamp1((langs_ge_1pct - 1) / 5)` | 6 or more languages with at least 1% of bytes |

- `files` = number of blobs. If files = 1, then log10 = 0 and size = 0.
- Round each component to 2 decimals and the total to 1 decimal.
- **Bands:** `score < 25` Low; `25 <= score < 50` Moderate; `50 <= score < 75` High; `score >= 75` Very high.
- **Caveat:** this is a structural complexity proxy built from file counts, nesting, byte sizes and language bytes. It is **not** based on lines of code or cyclomatic complexity, and the report must say so. Vendored or generated files inflate it.

**Worked example by hand.** A repo with 1,200 files, max depth 6, 18 files over 100 KB, and languages Python 85%, C 12%, Shell 2.5%, Makefile 0.5%:
- Size: log10(1200) = 3.0792. 3.0792 / 4 = 0.7698. × 25 = **19.24**
- Depth: 6 / 10 = 0.6. × 25 = **15.00**
- Large files: 18 / 1200 = 0.015. 0.015 / 0.10 = 0.15. × 25 = **3.75**
- Language spread: 3 languages are at 1% or more (Makefile 0.5% is excluded). (3 - 1) / 5 = 0.4. × 25 = **10.00**
- **Total = 48.0, which is Moderate.**

Tiny-repo sanity check, octocat/Hello-World (1 file `README`, depth 0, no languages): every component is 0, so the score is 0.0 (Low). Languages are empty, so spread = 0 with the note "language data unavailable".

---

## 6. Dependency health

### 6.1 Definitions (print these in the report)

- **Pinned** means the version is exact. For pip that is `==X` or `===X` with no `*`. For npm it is a bare `X.Y.Z[-pre]`, optionally prefixed with `=` or `v`.
- **Up-to-date** means pinned AND pinned version `==` registry latest (string equality after stripping a leading `v`/`=`). Anything else pinned is `outdated`.
- **Unpinned:**
  - A range spec gets state `unknown (range)`. The registry latest is still shown when it is within the cap.
  - Non-registry or unparsable specs (incl. `-e`, VCS, URL, local) get `unknown (unparsable)` with no lookup.
- **Healthy** means `pinned_pct >= 80` AND `uptodate_pct_of_pinned >= 80`.
  - `pinned_pct = pinned / total` (total = all declared dependencies, unknown included).
  - `uptodate_pct_of_pinned = up_to_date / pinned deps with a successful lookup`.
  - 0 deps -> `healthy None` ("Not applicable"). 0 pinned -> `healthy False`, note "no pinned dependencies".
- **Lookup cap:** at most **30** registry lookups per run: pinned deps first, then ranges.
  - If more, note "Checked 30 of N; pinned checked first".
  - If pinned deps were skipped, say "based on K of M pinned".
- **Registry calls** use plain `requests.get`, never the GitHub session (no token leak).

### 6.2 `requirements.txt` parsing (line by line)

1. Join lines ending with `\` to the next line.
2. Strip comments: remove `#` and everything after it **when the `#` is at line start or preceded by whitespace**. A `#` inside a URL fragment (`...#egg=x`) is not preceded by a space, so it survives.
3. Strip whitespace. Skip blank lines.
4. Option lines:
   - `-r` / `--requirement` / `-c` / `--constraint`: skip and add the note "nested file `<f>` not followed".
   - `-i`, `--index-url`, `--extra-index-url`, `-f`, `--find-links`, `--trusted-host`, `--no-binary`, `--only-binary`, `--pre`, `--require-hashes`: skip silently.
5. `-e <x>` / `--editable <x>` -> skip (same as the prompt; not counted).
6. VCS, URL or local path: the line starts with `git+`, `hg+`, `svn+`, `bzr+`, `http://`, `https://`, `file:`, `.`, or `/`, or contains ` @ ` (PEP 508 direct reference `name @ url`). State `unknown (unparsable)` (no lookup), with the name taken from before `@` or from `#egg=`.
7. Drop per-requirement options: cut at ` --hash=` and ` --global-option`.
8. Environment markers: split on the first `;` and keep the left part. Keep the marker text in `note` (e.g. `python_version < "3.8"`).
9. Match `^([A-Za-z0-9][A-Za-z0-9._-]*)\s*(\[[^\]]*\])?\s*(.*)$`. Group 1 is the name, group 2 the extras (dropped), group 3 the spec.
   - No match: `unknown (unparsable)`, with the raw line as the name.
10. Normalize the name for PyPI: `re.sub(r"[-_.]+", "-", name).lower()` (PEP 503).
11. Classify the spec:
    - `^===?\s*([^,*\s]+)$` -> pinned, with that version. `==1.4.*` contains `*`, so it is a range.
    - Empty spec -> range (shown as `any`).
    - Anything else (`>=`, `~=`, `<`, `!=`, `>`, comma lists) -> range.

Duplicates (same normalized name twice): keep the first and note the duplicate.

### 6.3 `package.json` parsing

- Read `dependencies` (kind `prod`) and `devDependencies` (kind `dev`). `peerDependencies` and `optionalDependencies` are not counted; note this in the README.
- If a key is missing, treat it as an empty dict. A value that is not a string means `unknown (unparsable)`.

Classify each spec `s` (after strip):

| Spec pattern | Example | pin |
|---|---|---|
| `^=?v?\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?(\+[0-9A-Za-z.-]+)?$` | `4.18.2`, `=1.0.0`, `v2.1.0-beta.1` | **pinned** |
| starts with `^` or `~`, contains `>` `<` `\|\|` ` - ` `x` `X` `*`, or is a partial `1` / `1.2` | `^4.18.2`, `~1.2.0`, `>=2 <3`, `1.x`, `*`, `1.2` | range |
| `""` or `latest` / `next` / any other dist-tag word (`^[A-Za-z][\w.-]*$` that is not a version) | `latest` | range (`tag: latest`) |
| `workspace:`, `file:`, `link:`, `portal:`, `npm:` (alias) | `workspace:^1.0.0`, `file:../lib` | not pinned, state `unknown (unparsable)` |
| `git+`, `git:`, `git://`, `github:`, `gitlab:`, `bitbucket:`, `http://`, `https://`, or `owner/repo[#ref]` (contains `/` and does not start with `@`) | `expressjs/body-parser#v2` | not pinned, state `unknown (unparsable)` |

Name for the npm URL: if it starts with `@`, replace the `/` with `%2F` (`@types/node` -> `@types%2Fnode`) **[V]**.

### 6.4 Version comparison without `packaging` (optional, only for the "behind" note; up-to-date uses `==`)

```python
def _key(v: str):
    # Strip a leading "v"/"=", cut build metadata at "+". Split off the pre-release at the first
    # "-" (npm) or at the first letter after the numeric part (pip: "1.2.0rc1", "2.0b2").
    # Numeric core -> tuple of ints padded to length 3: "2.0" -> (2,0,0).
    # Returns (core_tuple, is_final, pre_str), where is_final = 1 if there is no pre-release else 0,
    # so "1.0.0rc1" < "1.0.0". Returns None if the core has no leading digit.
def compare_versions(a, b) -> int | None:
    # Compare (core, is_final, pre_str) tuples; pre_str compares lexicographically (good enough).
    # Return None if either key is None (then simply omit the "behind" note).
```

- PyPI `info.version` is the latest release as listed by PyPI. npm `/latest` is the `latest` dist-tag.
- Post-releases (`1.0.post1`) and epochs (`1!2.0`) are not handled exactly. That is acceptable; list it in Limitations.
- Optional "behind" note: if the major part differs, "major behind"; else if the minor differs, "minor behind"; else "patch behind".

---

## 7. Report layout (rich) - OPTIONAL reference

The console is `Console(record=True)` with no fixed width; rich detects the terminal width. Optional / cut first: `--ascii` (chart `#`, `box.ASCII`) and the rate-limit footer line below.

```
╭──────────────────── Repository Analysis: psf/requests ────────────────────╮
│ A simple, yet elegant, HTTP library.                                       │
│ ★ 52,000  forks 9,000  default branch: main  analyzed 2026-11-05 12:00 UTC │
╰───────────────────────────────────────────────────────────────────────────╯
╭─ 1. Tech stack ─────────────────────────────────────────────────────────────╮
│ Table: Name | Category | Evidence                                            │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ 2. File structure ─────────────────────────────────────────────────────────╮
│ 312 files · 41 dirs · max depth 5 · 4.8 MB                                   │
│ Table A: Top-level entry | Kind | Files                                      │
│ Table B: Extension | Files | %          Table C: Largest files (path, size)  │
│ Key files: README ✓ LICENSE ✓ tests ✓ CI ✓ docs ✓                            │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ 3. Code complexity: 48.0 / 100 (Moderate) ─────────────────────────────────╮
│ Table: Component | Measured | Formula | Points (/25)                         │
│ Bands: <25 Low · 25-50 Moderate · 50-75 High · 75+ Very high                 │
│ Note: structural proxy from Git tree file counts/bytes, not lines of code.  │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ 4. Dependency health: Not healthy ─────────────────────────────────────────╮
│ Definition line (6.1) · Summary: 28 deps · 1 pinned (3.6%) · 0/1 up to date  │
│ Table: Package | Type | Spec | Latest | State   (state coloured)             │
│ Notes: lookup cap, nested files not followed                                 │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ 5. Contribution activity (default branch) ─────────────────────────────────╮
│ 143 commits in 52 weeks · 31 active weeks                                    │
│ 2026-08-16 │██████████▌                         7                            │
│ 2026-08-23 │████████████████████████████████▉  19                            │
│ ... (last 12 weeks)                                                          │
│ Top 5 contributors (all-time commits, GitHub API)                            │
│ nateprewitt  │██████████████████████  802                                     │
╰──────────────────────────────────────────────────────────────────────────────╯
(optional footer) GitHub API calls: 6 · rate limit remaining: 54/60 (resets 13:00 UTC) · token: no
```

- Sections are `rich.panel.Panel` with the title `"N. Name"`. Tables use `rich.table.Table(box=box.SIMPLE_HEAVY)`.
- An unavailable section is a Panel with a yellow border whose body is `Not available: <reason>`. A section is never omitted.
- **Bar chart** (no plotting library):
  - `width = 40`, `blocks = " ▏▎▍▌▋▊▉█"`.
  - For value `v` with `vmax = max(values)`, `units = v / vmax * width * 8`. Draw `"█" * (units // 8)`, then `blocks[units % 8]` if the remainder is above 0, then pad to `width`, then the number.
  - A row with `v > 0` always shows at least `▏`, so a small non-zero value never looks like zero.
  - If `vmax == 0`, draw empty bars (avoid dividing by zero) and show the note `No commits in the last 52 weeks.`
- State colours: up-to-date = green, outdated = red, unknown = yellow.
- Optional footer: `rich.text.Text` in dim style. Rate data comes from the **last** GitHub response headers. Missing values print `?`.
- Windows: redirected output (`*> file`) uses cp1252 and the hand-drawn `█▏` characters crash with `UnicodeEncodeError`. `main()` reconfigures stdout to UTF-8 (section 3.8), and the demo sets `$env:PYTHONUTF8 = "1"`.

---

## 8. Known limitations (copy into the README)

1. Manifests are read only at the **repo root**, and only `requirements.txt` and `package.json`. `pyproject.toml`, `setup.py`, `Pipfile`, lock files, `go.mod`, nested `-r` files and monorepo sub-packages are detected but not parsed.
2. The complexity score is a **structural proxy** (file count, depth, byte sizes, language bytes). It does not count lines of code and does not do static analysis.
3. Language percentages are GitHub Linguist **bytes**, which excludes vendored and generated files according to Linguist rules.
4. Very large repos: the Git tree is truncated above 100,000 entries or 7 MB, so structure and complexity become lower bounds and are flagged. Contributor lists may be unavailable for huge repos.
5. Commit activity covers the **default branch, last 52 weeks**, as computed and cached by GitHub. The first request may return 202, which triggers a retry for about 15 s, then reports "Not available".
6. Contributors shown are the top 5 (of 10 fetched) by all-time commit count. Anonymous (email-only) contributors are excluded. The data may be hours old.
7. Dependency health:
   - Unpinned ranges cannot be judged "up to date", so they are shown as `unknown (range)`.
   - Version comparison is simplified (no PEP 440 epochs or post-releases).
   - At most 30 registry lookups are made.
   - `peerDependencies` and `optionalDependencies` are ignored.
8. Without `GITHUB_TOKEN` the limit is 60 requests/hour per IP, about 5 analyses per hour. Private repos are reported as "not found".
9. Files over 1 MB cannot be read through the contents API.
10. Every number comes from the GitHub, PyPI or npm APIs at run time. Nothing is estimated or filled in.

---

## 9. Verification log

Verified on docs.github.com and live (2026-11-05):
- **commit_activity:** 202 means the background job is computing, so wait and retry. 204 is documented. The shape is `{week, total, days}`, with days starting Sunday.
- **Git trees:** `recursive` takes any value, the `truncated` flag exists, the limit is 100,000 entries / 7 MB, and 409 is listed as "Conflict".
- **Rate limits:** the headers are `x-ratelimit-limit/remaining/used/reset/resource`. The limits are 60/hour unauthenticated and 5,000/hour authenticated. A primary limit returns 403 **or** 429 with remaining 0. A secondary limit returns 403/429 with an optional `retry-after`; the guidance is to wait at least 60 s when the header is absent.
- **Contributors:** `per_page` max is 100, results are sorted by commits descending, 204 means an empty repo, and data is cached.
- **Contents:** files of 1 MB or less are fully supported. Files of 1-100 MB return `content` as an empty string with `encoding: "none"`.
- **npm:** `https://registry.npmjs.org/@types%2Fnode/latest` returns `name` and `version`.

Not verified (treat defensively; check during stage tests):
- That 409 on the trees endpoint specifically means "Git Repository is empty". It is widely observed, but the docs only say "Conflict". The code should show GitHub's `message` field in the reason, so the output stays truthful either way.
- That a 403 from `/contributors` on huge repos means "list too large". Show GitHub's `message` verbatim instead of asserting a cause.
- That `/stats/commit_activity` behaves for repos with 10,000+ commits. The docs note that limit only for `code_frequency` and `contributors` stats.
- That `/git/trees/{branch}` works when the default branch name contains `/`. Fallback: on 404, call `GET /repos/{o}/{r}/branches/{branch}` and use `commit.commit.tree.sha` (1 extra call).
- That PyPI `info.version` excludes pre-releases. This is generally true but not guaranteed.
