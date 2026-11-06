# Task 4 (Track B): GitHub Repository Analyzer CLI - Plan Index

**Goal:** `python analyze.py <github-repo-url>` prints a 5-section terminal report (tech stack with evidence,
file structure, complexity score + formula, dependency health + "healthy" definition, weekly commit chart +
top contributors). Python 3.12, `requests` + `rich` + stdlib only. Never invent data: `Not available: <reason>`.
Graded through the exported AI chat (40 marks).

**Docs:** [plan/STAGE_PROMPTS.md](plan/STAGE_PROMPTS.md) (paste these; they win on names and shapes) -
[plan/SPEC.md](plan/SPEC.md) (reference for edge cases; read its TL;DR only unless a test fails).

## Folder layout
```
task4/
  PLAN.md                 this index
  analyze.py              CLI: argparse, exit codes 0/1/2/3/4/5/6, --save
  analyzer/__init__.py
  analyzer/github_client.py  parse_repo_url, GitHubClient.get, errors, GITHUB_TOKEN from env
  analyzer/fetch.py       fetch_bundle(): every GitHub call, once, per-call try/except
  analyzer/techstack.py   detect_stack(bundle)         pure
  analyzer/structure.py   summarize_structure(bundle)  pure
  analyzer/complexity.py  score_complexity(bundle)     pure
  analyzer/deps.py        analyze_deps(bundle)         PyPI/npm lookups (no token sent)
  analyzer/activity.py    analyze_activity(bundle)     pure
  analyzer/report.py      render(console, repo_meta, sections, token_used)
  README.md               Track B, libraries, how to run, definitions, limits
  plan/                   SPEC.md, STAGE_PROMPTS.md
  demo/                   psf_requests.txt, expressjs_express.txt, hello_world.txt (+ failures.txt)
```

## Architecture
```
 analyze.py (CLI, exit codes)
      |  parse_repo_url(url) -> (owner, repo)        InvalidRepoURL -> exit 2
      v
 GitHubClient (token from env, timeout 15, error mapping: 404 gate->3, rate->4, 401->5, net->6)
      |
      v
 fetch_bundle()  -- GET /repos, /languages, /git/trees?recursive=1, /contents (root manifests),
      |              /stats/commit_activity (202 retry x5), /contributors?per_page=10
      v
 bundle (flat dict: repo, languages, tree, files, commit_activity, contributors, *_error)
      |
      +--> detect_stack ------+
      +--> summarize_structure+
      +--> score_complexity --+-->  sections {status, reason, ...}
      +--> analyze_deps ------+     (deps alone calls PyPI / npm)
      +--> analyze_activity --+
                               v
                     report.render()  ->  terminal (+ --save demo/*.txt)
```

## Build order (finish Task 4 by 13:20 so 30-40 min stay for Task 1 before 14:00)
Start no later than 11:28. Running totals from STAGE_PROMPTS.md:

| Stage | Work | Box | Done by |
|---|---|---|---|
| 0 | Token setup + planning prompt | 7 min | +0:07 |
| 1 | CLI + GitHub client, error/exit codes | 15 min | +0:22 |
| 2 | fetch_bundle + tech stack | 12 min | +0:34 |
| 3 | File structure | 13 min | +0:47 |
| 4 | Complexity score | 12 min | +0:59 |
| 5 | Dependency health | 13 min | +1:12 |
| 6 | Contribution activity | 15 min | +1:27 |
| 7 | report.py, README, 3 demo runs | 15 min | +1:42 |
| - | Failure demo in chat + /export | 10 min | +1:52 |

Behind schedule? Use the Cut list at the end of STAGE_PROMPTS.md. Never cut error handling or "Not available".

## Grading checklist
- [ ] README states "Track B: GitHub Repository Analyzer"
- [ ] README lists libraries (requests, rich, stdlib) and how to run in PowerShell
- [ ] Planning prompt (Stage 0) and at least one push-back in the chat
- [ ] Each stage: real terminal output pasted back, focused fix asked when wrong
- [ ] Failure case shown in chat (invalid URL, not found, bad token, no manifest)
- [ ] At least 2 demo runs saved in `demo/` (plan: requests, express, Hello-World)
- [ ] Complexity formula and "healthy" definition printed in the report
- [ ] Token never pasted in the chat or hard-coded
- [ ] Chat exported (`/export`) and saved next to `task4/`
