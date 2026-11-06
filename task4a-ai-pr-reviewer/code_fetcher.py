"""Thin GitHub REST client. Token comes from GITHUB_TOKEN and is never printed."""
import requests

import config


class GitHubError(Exception):
    pass


API = "https://api.github.com"


def gh(method, path, **kw):
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    headers.update(kw.pop("headers", None) or {})
    token = config.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    kw.setdefault("timeout", 30)
    url = path if path.startswith("http") else API + path
    try:
        r = requests.request(method, url, headers=headers, **kw)
    except requests.RequestException as e:
        raise GitHubError(f"GitHub {method} {path} failed: {type(e).__name__}") from e
    if r.status_code >= 400:
        try:
            msg = r.json().get("message", "")
        except ValueError:
            msg = (r.text or "")[:200]
        raise GitHubError(f"GitHub {method} {path} -> {r.status_code}: {msg}")
    return r


def fetch_pr(repo, number):
    d = gh("GET", f"/repos/{repo}/pulls/{number}").json()
    return {"number": d.get("number", number), "title": d.get("title", ""),
            "head_ref": (d.get("head") or {}).get("ref", ""),
            "head_sha": (d.get("head") or {}).get("sha", ""),
            "base_ref": (d.get("base") or {}).get("ref", ""),
            "state": d.get("state", ""), "merged": bool(d.get("merged"))}


def fetch_diff(repo, number):
    r = gh("GET", f"/repos/{repo}/pulls/{number}", headers={"Accept": "application/vnd.github.diff"})
    return r.text
