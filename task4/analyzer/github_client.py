"""GitHub REST client: URL parsing, authenticated GET, error mapping.

The token is read only from the GITHUB_TOKEN environment variable and is never
printed or logged.
"""

from __future__ import annotations

import os
import re
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit

import requests

API_BASE = "https://api.github.com"
TIMEOUT = 15
USER_AGENT = "rc3-repo-analyzer"

_OWNER_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
_REPO_RE = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
_GATE_RE = re.compile(r"^/repos/[^/]+/[^/]+/?$")
_EXPECTED = "Expected e.g. https://github.com/owner/repo"


# --------------------------------------------------------------------------- errors

class AnalyzerError(Exception):
    """Base error. `status` is the HTTP status when one is known."""

    exit_code = 1

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class InvalidRepoURL(AnalyzerError):
    exit_code = 2


class RepoNotFound(AnalyzerError):
    exit_code = 3

    def __init__(self, message: str):
        super().__init__(message, status=404)


class RateLimitError(AnalyzerError):
    exit_code = 4

    def __init__(self, reset_epoch: int | None = None, retry_after: int | None = None,
                 limit: int | None = None):
        self.reset_epoch = reset_epoch
        self.retry_after = retry_after
        self.limit = limit
        if reset_epoch is not None:
            mins = max(0, round((reset_epoch - time.time()) / 60))
            lim = f"{limit}/hour" if limit else "limit"
            msg = (f"GitHub API rate limit exceeded ({lim}). Resets at {format_utc_hhmm(reset_epoch)} UTC "
                   f"(in {mins} min). Set GITHUB_TOKEN to get 5,000 requests/hour: "
                   f'$env:GITHUB_TOKEN = "<your token>"')
        else:
            wait = retry_after if retry_after is not None else 60
            msg = f"GitHub secondary rate limit hit. Wait {wait} seconds and try again."
        super().__init__(msg, status=403)

    def short(self) -> str:
        """One-line reason used for sections after the gate call."""
        if self.reset_epoch is not None:
            return f"GitHub rate limit reached (resets {format_utc_hhmm(self.reset_epoch)} UTC)"
        wait = self.retry_after if self.retry_after is not None else 60
        return f"GitHub rate limit reached (retry in {wait} s)"


class AuthError(AnalyzerError):
    exit_code = 5

    def __init__(self, message: str):
        super().__init__(message, status=401)


class NetworkError(AnalyzerError):
    exit_code = 6


def format_utc_hhmm(epoch: int) -> str:
    return datetime.fromtimestamp(int(epoch), tz=timezone.utc).strftime("%H:%M")


# --------------------------------------------------------------------------- URL parsing

def parse_repo_url(url: str) -> tuple[str, str]:
    """Return (owner, repo) from a GitHub repository URL, or raise InvalidRepoURL."""
    original = url
    if not isinstance(url, str):
        raise InvalidRepoURL(f"'{original}' is not a GitHub repository URL. {_EXPECTED}")
    s = url.strip().strip("'\"").strip()
    if s.lower().startswith("git@github.com:"):
        s = "https://github.com/" + s[len("git@github.com:"):]
    if "://" not in s:
        s = "https://" + s
    try:
        parts = urlsplit(s)
    except ValueError:
        raise InvalidRepoURL(f"'{original}' is not a GitHub repository URL. {_EXPECTED}") from None
    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if parts.scheme not in ("http", "https") or host != "github.com":
        raise InvalidRepoURL(f"'{original}' is not a GitHub repository URL. {_EXPECTED}")
    segs = [p for p in parts.path.split("/") if p]
    if len(segs) < 2:
        raise InvalidRepoURL(f"'{original}' is not a GitHub repository URL. {_EXPECTED}")
    owner, repo = segs[0], segs[1]
    if repo.lower().endswith(".git"):
        repo = repo[:-4]
    if not _OWNER_RE.match(owner) or not _REPO_RE.match(repo) or repo in (".", ".."):
        raise InvalidRepoURL(f"'{original}' is not a GitHub repository URL. {_EXPECTED}")
    return owner, repo


# --------------------------------------------------------------------------- client

def _message(resp: requests.Response) -> str:
    try:
        data = resp.json()
        if isinstance(data, dict) and data.get("message"):
            return str(data["message"])
    except ValueError:
        pass
    return (resp.reason or "").strip() or "no message"


def _int_or_none(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class GitHubClient:
    """Thin wrapper around requests.Session for the GitHub REST API."""

    def __init__(self, token: str | None = None):
        if token is None:
            token = os.environ.get("GITHUB_TOKEN", "")
        token = (token or "").strip()
        self._token = token or None
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": USER_AGENT,
        })
        if self._token:
            self.session.headers["Authorization"] = f"Bearer {self._token}"
        self.rate: dict = {"remaining": None, "limit": None, "reset_epoch": None}
        self.calls = 0

    @property
    def token_used(self) -> bool:
        return self._token is not None

    def __repr__(self) -> str:  # never expose the token
        return f"GitHubClient(token_used={self.token_used}, calls={self.calls})"

    def get(self, path: str, params: dict | None = None) -> requests.Response:
        """GET an API path. Returns 2xx and 409 responses unchanged; raises otherwise."""
        if path.startswith("http") and not path.startswith(API_BASE + "/"):
            # The session carries the token: never send it anywhere but api.github.com.
            raise AnalyzerError("refusing to send a GitHub request to a non-GitHub URL")
        url = path if path.startswith("http") else API_BASE + path
        try:
            resp = self.session.get(url, params=params, timeout=TIMEOUT)
        except (requests.Timeout, requests.ConnectionError) as e:
            raise NetworkError(
                f"Network error: could not reach api.github.com ({type(e).__name__}). "
                "Check your internet connection."
            ) from None
        except requests.RequestException as e:
            raise NetworkError(f"Network error: request failed ({type(e).__name__}).") from None
        finally:
            self.calls += 1

        h = resp.headers
        self.rate = {
            "remaining": _int_or_none(h.get("x-ratelimit-remaining")),
            "limit": _int_or_none(h.get("x-ratelimit-limit")),
            "reset_epoch": _int_or_none(h.get("x-ratelimit-reset")),
        }

        status = resp.status_code
        if 200 <= status < 300 or status == 409:
            return resp

        msg = _message(resp)
        if status == 401:
            if self._token:
                raise AuthError("GITHUB_TOKEN was rejected by GitHub (401 Bad credentials). "
                                "Fix it or remove it (Remove-Item Env:GITHUB_TOKEN, "
                                "or edit the GITHUB_TOKEN line in .env)")
            raise AuthError(f"GitHub returned 401 Unauthorized: {msg}")
        if status in (403, 429):
            if h.get("x-ratelimit-remaining") == "0":
                raise RateLimitError(reset_epoch=_int_or_none(h.get("x-ratelimit-reset")),
                                     limit=_int_or_none(h.get("x-ratelimit-limit")))
            if h.get("retry-after") is not None or "secondary rate limit" in msg.lower():
                ra = _int_or_none(h.get("retry-after"))
                raise RateLimitError(retry_after=ra if ra is not None else 60)
        if status == 404 and _GATE_RE.match(path):
            full = path.strip("/").split("/", 1)[1]
            raise RepoNotFound(f"Repository not found: {full} (check spelling, or it may be private)")
        raise AnalyzerError(f"GitHub returned {status}: {msg}", status=status)
