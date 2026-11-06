<div align="center">

# 🏆 RC3 AI Hackathon 2026

**My solutions to the RC3 AI Hackathon, Riphah International University, 5 November 2026**

### 🥇 Winner: 1st Position 🥇

![1st Place](https://img.shields.io/badge/RC3%20AI%20Hackathon%202026-%F0%9F%A5%87%201st%20Place-FFD700?style=for-the-badge)

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![Gemini](https://img.shields.io/badge/LLM-Google%20Gemini-4285F4?logo=google&logoColor=white)
![GitHub API](https://img.shields.io/badge/GitHub-REST%20API-181717?logo=github)
![Tests](https://img.shields.io/badge/offline%20tests-150%2B%20passing-2ea44f)

</div>

---

## 📦 What's inside

| # | Project | What it does | Stack |
|:-:|---|---|---|
| 1 | [**Jira Ticket Generator**](task1-jira-ticket-generator/) | Turns a raw client brief into epics, Jira tickets and open questions. It **never assumes**: anything the brief doesn't say becomes an open question. | Gemini · pytest |
| 2 | [**Near-Duplicate Detection**](task2-near-duplicate-detection/) | Finds every pair of documents with Jaccard ≥ 0.8 on 5-word shingles, across 112k documents in under 15 minutes. | NumPy · MinHash · LSH |
| 4A | [**AI PR Reviewer**](task4a-ai-pr-reviewer/) | When code is pushed, it opens a PR, reads the Jira ticket and the diff, asks an LLM whether the acceptance criteria are met, then **merges** or **blocks** the PR. | GitHub API · Gemini · webhooks |
| 4B | [**GitHub Repo Analyzer**](task4b-github-repo-analyzer/) | `python analyze.py <repo-url>` prints a terminal report: tech stack, file structure, complexity score, dependency health and a commit-activity chart. | requests · rich |

> **Step-by-step instructions for every project are in [`GUIDE.md`](GUIDE.md).**

---

## ⚡ Quick start

```powershell
git clone https://github.com/umarahad2005/rc3-ai-hackathon-2026.git
cd rc3-ai-hackathon-2026
$REPO = (Get-Location).Path
```

| Project | Install | Run |
|---|---|---|
| Task 1 | `pip install -r task1-jira-ticket-generator\requirements.txt` | `python main.py briefs\clear.txt --out out\clear` |
| Task 2 | `pip install -r task2-near-duplicate-detection\requirements.txt` | Open `Task2_NearDuplicates_final.ipynb` in Colab |
| Task 4A | `pip install -r task4a-ai-pr-reviewer\requirements.txt` | `python start.py`, then just `git push` |
| Task 4B | `pip install -r task4b-github-repo-analyzer\requirements.txt` | `python analyze.py https://github.com/psf/requests` |

You need **Python 3.10+**. Tasks 1 and 4A need a free [Gemini API key](https://aistudio.google.com), and Task 4A needs the [GitHub CLI](https://cli.github.com).

---

## 🤖 Task 4A in one picture

```
 git push feature/RC3-20-x
          │
          ▼
 ┌─────────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────────┐
 │ open PR (auto)  │──▶│ find ticket  │──▶│ fetch diff   │──▶│ Gemini: are all  │
 │ start.py watch  │   │ RC3-20 → AC  │   │ GitHub API   │   │ AC fulfilled?    │
 └─────────────────┘   └──────────────┘   └──────────────┘   └────────┬─────────┘
                                                                     │
                                 ┌───────────────────────────────────┴────────┐
                                 ▼                                            ▼
                     ✅ status Success + comment                 ❌ status Failed + comment
                        + squash-merge                              listing what is missing
```

---

## 🗂️ Repository layout

```
rc3-ai-hackathon-2026/
├── GUIDE.md                        ← full setup and run guide
├── task1-jira-ticket-generator/    ← Task 1: brief → Jira tickets
├── task2-near-duplicate-detection/ ← Task 2: MinHash + LSH notebook
├── task4a-ai-pr-reviewer/          ← Task 4 Track A: automated PR reviewer
├── task4b-github-repo-analyzer/    ← Task 4 Track B: repo analyzer CLI
└── chats/                          ← AI chat exports (planning and build sessions)
```

---

## 🔐 Security and what's not included

- **No secrets:** there is no `.env` or `.env.example` in this repo (`.gitignore` blocks them). Every key is read from environment variables or a local `.env` you create yourself. See [`GUIDE.md`](GUIDE.md#-secrets).
- **Chat exports:** a GitHub token pasted during a session is replaced with `[REDACTED]`.
- **Organiser material:** the datasets, answer keys, generator scripts and handbook belong to the organisers and are not published.

<div align="center">

Built with ❤️ and [Claude Code](https://claude.com/claude-code) by [@umarahad2005](https://github.com/umarahad2005)

</div>
