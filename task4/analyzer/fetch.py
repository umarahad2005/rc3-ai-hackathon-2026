"""fetch_bundle(): every GitHub call for one run happens here, exactly once.

Only the GET /repos/{o}/{r} gate call may raise. Every later call is isolated:
an AnalyzerError (or a malformed response) is stored as a human-readable string in
the matching *_error key. After the first RateLimitError no more calls are made.
No section-specific logic lives here.
"""

from __future__ import annotations

import base64
import time
from urllib.parse import quote

from .github_client import AnalyzerError, GitHubClient, RateLimitError

ROOT_MANIFESTS = ("requirements.txt", "package.json")
SKIP_DIRS = {"node_modules", "vendor", "venv", ".venv", "site-packages", "dist", "build"}
MAX_NESTED_PER_KIND = 2
STATS_BACKOFF = (1, 2, 3, 4, 5)  # seconds between retries on 202
EMPTY_204 = "no data (empty repo)"
STATS_PENDING = "GitHub is still computing statistics, try again in a minute"


class _Stop(Exception):
    """Internal: a rate limit was hit, skip every remaining call."""


def fetch_bundle(client: GitHubClient, owner: str, repo: str) -> dict:
    base = f"/repos/{owner}/{repo}"

    # Gate call: may raise RepoNotFound / AuthError / RateLimitError / NetworkError.
    meta = client.get(base).json()

    bundle: dict = {
        "repo": meta,
        "languages": None, "languages_error": None,
        "tree": None, "tree_truncated": False, "tree_error": None,
        "files": {},
        "files_errors": {},  # extra (additive): {path: reason} for manifests that could not be read
        "commit_activity": None, "activity_error": None,
        "contributors": None, "contributors_error": None,
    }
    state = {"rate_reason": None}

    def call(path: str, params: dict | None = None):
        """GET that converts a rate limit into _Stop and remembers the reason."""
        if state["rate_reason"]:
            raise _Stop()
        try:
            return client.get(path, params)
        except RateLimitError as e:
            state["rate_reason"] = e.short()
            raise _Stop() from None

    # ---- languages
    try:
        r = call(f"{base}/languages")
        if r.status_code == 204:
            bundle["languages_error"] = EMPTY_204
        else:
            data = r.json()
            if not isinstance(data, dict):
                bundle["languages_error"] = "unexpected response from GitHub languages API"
            else:
                bundle["languages"] = data
                if not data:
                    bundle["languages_error"] = "GitHub detected no languages"
    except _Stop:
        pass
    except AnalyzerError as e:
        bundle["languages_error"] = str(e)
    except ValueError:
        bundle["languages_error"] = "invalid JSON from GitHub languages API"

    # ---- tree (one recursive call on the default branch)
    branch = meta.get("default_branch") if isinstance(meta, dict) else None
    tree_empty_repo = False
    if not branch:
        bundle["tree_error"] = "Repository has no default branch (it may be empty)"
        tree_empty_repo = True
    else:
        try:
            r = call(f"{base}/git/trees/{quote(branch, safe='')}", {"recursive": "1"})
            if r.status_code == 409:
                bundle["tree_error"] = "Repository is empty (GitHub returned 409)"
                tree_empty_repo = True
            elif r.status_code == 204:
                bundle["tree_error"] = EMPTY_204
                tree_empty_repo = True
            else:
                data = r.json()
                entries = data.get("tree") if isinstance(data, dict) else None
                if not isinstance(entries, list):
                    bundle["tree_error"] = "unexpected response from GitHub trees API"
                else:
                    bundle["tree"] = [
                        {"path": e.get("path"), "type": e.get("type"), "size": e.get("size")}
                        for e in entries if isinstance(e, dict) and e.get("path")
                    ]
                    bundle["tree_truncated"] = bool(data.get("truncated"))
        except _Stop:
            pass
        except AnalyzerError as e:
            if e.status == 404:
                bundle["tree_error"] = "default branch tree not found (GitHub returned 404)"
            else:
                bundle["tree_error"] = str(e)
        except ValueError:
            bundle["tree_error"] = "invalid JSON from GitHub trees API"

    # ---- root manifests via /contents (only if present in the tree)
    if bundle["tree"] is not None:
        root_blobs = {e["path"] for e in bundle["tree"] if e["type"] == "blob" and "/" not in e["path"]}
        candidates = [p for p in ROOT_MANIFESTS if p in root_blobs]
        # No root manifest of a kind: use the shallowest ones in sub-folders (max 2 per kind),
        # e.g. frontend/package.json, backend/requirements.txt. Vendored folders are skipped.
        for name in ROOT_MANIFESTS:
            if name in root_blobs:
                continue
            nested = sorted(
                (e["path"] for e in bundle["tree"]
                 if e["type"] == "blob" and e["path"].endswith("/" + name)
                 and not any(s in e["path"].split("/") for s in SKIP_DIRS)),
                key=lambda p: (p.count("/"), p.lower()))
            candidates += nested[:MAX_NESTED_PER_KIND]
    elif tree_empty_repo:
        candidates = []
    else:
        candidates = list(ROOT_MANIFESTS)  # tree unknown: try both, 404 = absent
    for path in candidates:
        try:
            r = call(f"{base}/contents/{path}", {"ref": branch} if branch else None)
            data = r.json() if r.status_code != 204 else None
            if not isinstance(data, dict):
                bundle["files_errors"][path] = f"{path}: unexpected response from GitHub contents API"
                continue
            content = data.get("content") or ""
            if data.get("encoding") != "base64" or not content:
                bundle["files_errors"][path] = f"{path} is larger than 1 MB and was not parsed"
                continue
            bundle["files"][path] = base64.b64decode(content).decode("utf-8", "replace")
        except _Stop:
            break
        except AnalyzerError as e:
            if e.status == 404 and bundle["tree"] is None:
                continue  # absent
            bundle["files_errors"][path] = str(e)
        except ValueError:
            bundle["files_errors"][path] = f"{path}: could not decode file content"

    # ---- weekly commit activity (202 -> retry with backoff)
    try:
        r = call(f"{base}/stats/commit_activity")
        for delay in STATS_BACKOFF:
            if r.status_code != 202:
                break
            time.sleep(delay)
            r = call(f"{base}/stats/commit_activity")
        if r.status_code == 202:
            bundle["activity_error"] = STATS_PENDING
        elif r.status_code == 204:
            bundle["activity_error"] = EMPTY_204
        elif r.status_code == 409:
            bundle["activity_error"] = "Repository is empty (GitHub returned 409)"
        else:
            data = r.json()
            if isinstance(data, list):
                bundle["commit_activity"] = data
            else:
                bundle["activity_error"] = "unexpected response from GitHub stats API"
    except _Stop:
        pass
    except AnalyzerError as e:
        bundle["activity_error"] = str(e)
    except ValueError:
        bundle["activity_error"] = "invalid JSON from GitHub stats API"

    # ---- top contributors (all-time)
    try:
        r = call(f"{base}/contributors", {"per_page": 10})
        if r.status_code == 204:
            bundle["contributors_error"] = EMPTY_204
        elif r.status_code == 409:
            bundle["contributors_error"] = "Repository is empty (GitHub returned 409)"
        else:
            data = r.json()
            if isinstance(data, list):
                bundle["contributors"] = data
            else:
                bundle["contributors_error"] = "unexpected response from GitHub contributors API"
    except _Stop:
        pass
    except AnalyzerError as e:
        if e.status == 403:
            bundle["contributors_error"] = f"contributor list too large for GitHub to compute ({e})"
        else:
            bundle["contributors_error"] = str(e)
    except ValueError:
        bundle["contributors_error"] = "invalid JSON from GitHub contributors API"

    # ---- after a rate limit: every still-unset error gets the rate-limit reason
    if state["rate_reason"]:
        reason = state["rate_reason"]
        if bundle["languages"] is None and not bundle["languages_error"]:
            bundle["languages_error"] = reason
        if bundle["tree"] is None and not bundle["tree_error"]:
            bundle["tree_error"] = reason
        if bundle["commit_activity"] is None and not bundle["activity_error"]:
            bundle["activity_error"] = reason
        if bundle["contributors"] is None and not bundle["contributors_error"]:
            bundle["contributors_error"] = reason
        for path in candidates:
            if path not in bundle["files"] and path not in bundle["files_errors"]:
                bundle["files_errors"][path] = reason
        bundle["rate_limited"] = reason
    return bundle
