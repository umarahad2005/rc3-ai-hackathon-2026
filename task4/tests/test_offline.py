"""Offline tests: fake GitHub responses, no network, no token needed.

Run from task4/:   python -m unittest -v tests.test_offline
They prove the failure paths that are hard to trigger live (rate limit, 202 "still computing",
network error) and that missing data is reported as "Not available" instead of being invented.
"""
import base64
import io
import json
import os
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import analyze  # noqa: E402
from analyzer.github_client import InvalidRepoURL, parse_repo_url  # noqa: E402


def resp(status=200, body=None, headers=None):
    r = requests.Response()
    r.status_code = status
    r._content = json.dumps(body if body is not None else {}).encode()
    r.headers.update({"x-ratelimit-remaining": "4999", "x-ratelimit-limit": "5000",
                      "x-ratelimit-reset": "1893456000", **(headers or {})})
    return r


REPO = {"full_name": "o/r", "description": "demo", "default_branch": "main",
        "stargazers_count": 1, "forks_count": 0, "size": 10}


def router(routes):
    """Fake Session.get: the first route whose key is a suffix of the URL path answers."""
    def fake_get(self, url, params=None, timeout=None):
        path = url.split("api.github.com", 1)[-1]
        for key, value in routes.items():
            if path.endswith(key):
                return value() if callable(value) else value
        return resp(404, {"message": "Not Found"})
    return fake_get


def run(argv, routes):
    out, err = io.StringIO(), io.StringIO()
    env = {k: v for k, v in os.environ.items() if k != "GITHUB_TOKEN"}
    with mock.patch.dict(os.environ, env, clear=True), \
         mock.patch("analyze.load_env_file"), \
         mock.patch("requests.Session.get", router(routes)), \
         mock.patch("time.sleep"), \
         redirect_stdout(out), redirect_stderr(err):
        code = analyze.main(argv)
    return code, out.getvalue()


class UrlParsing(unittest.TestCase):
    def test_valid_forms(self):
        for u in ["https://github.com/psf/requests", "http://github.com/psf/requests/",
                  "github.com/psf/requests.git", "https://github.com/psf/requests/tree/main/src"]:
            self.assertEqual(parse_repo_url(u), ("psf", "requests"), u)

    def test_invalid_forms(self):
        for u in ["not-a-url", "https://gitlab.com/a/b", "https://github.com/onlyowner", ""]:
            with self.assertRaises(InvalidRepoURL, msg=u):
                parse_repo_url(u)


class ErrorPaths(unittest.TestCase):
    def test_rate_limit_exit_4(self):
        limited = resp(403, {"message": "API rate limit exceeded"},
                       {"x-ratelimit-remaining": "0", "x-ratelimit-limit": "60"})
        code, out = run(["https://github.com/o/r"], {"/repos/o/r": limited})
        self.assertEqual(code, 4)
        self.assertIn("rate limit", out.lower())
        self.assertNotIn("Traceback", out)

    def test_not_found_exit_3(self):
        code, out = run(["https://github.com/o/r"], {})
        self.assertEqual(code, 3)
        self.assertIn("Repository not found", out)

    def test_bad_token_exit_5(self):
        bad = resp(401, {"message": "Bad credentials"})
        with mock.patch.dict(os.environ, {"GITHUB_TOKEN": "bad"}):
            out = io.StringIO()
            with mock.patch("analyze.load_env_file"), mock.patch("requests.Session.get", router({"/repos/o/r": bad})), \
                 redirect_stdout(out), redirect_stderr(io.StringIO()):
                code = analyze.main(["https://github.com/o/r"])
        self.assertEqual(code, 5)
        self.assertNotIn("bad\n", out.getvalue())  # token value is never echoed

    def test_network_error_exit_6(self):
        def boom():
            raise requests.ConnectionError("offline")
        code, out = run(["https://github.com/o/r"], {"/repos/o/r": boom})
        self.assertEqual(code, 6)
        self.assertIn("Network error", out)

    def test_invalid_url_exit_2(self):
        code, out = run(["not-a-url"], {})
        self.assertEqual(code, 2)
        self.assertIn("Invalid URL", out)


class NeverInvent(unittest.TestCase):
    PKG = base64.b64encode(json.dumps({"dependencies": {"left-pad": "1.3.0"}}).encode()).decode()

    def routes(self, **over):
        pkg = self.PKG
        r = {
            "/repos/o/r": resp(200, REPO),
            "/repos/o/r/languages": resp(200, {"Python": 900, "Shell": 100}),
            "/git/trees/main": resp(200, {"truncated": False, "tree": [
                {"path": "src", "type": "tree"}, {"path": "src/app.py", "type": "blob", "size": 1200},
                {"path": "README.md", "type": "blob", "size": 300}]}),
            "/stats/commit_activity": resp(202, {}),  # GitHub still computing, every time
            "/contributors": resp(200, [{"login": "alice", "contributions": 7}]),
        }
        r.update(over)
        return r, pkg

    def test_202_stats_reported_not_available(self):
        routes, _ = self.routes()
        code, out = run(["https://github.com/o/r"], routes)
        self.assertEqual(code, 0)
        self.assertIn("Not available", out)
        self.assertIn("alice", out)              # contributors still shown
        self.assertNotIn("0 commits in the last 52", out)  # no fake zero

    def test_no_manifest_reported(self):
        routes, _ = self.routes()
        code, out = run(["https://github.com/o/r"], routes)
        self.assertIn("No requirements.txt or package.json found", out)

    def test_nested_manifest_and_registry_failure(self):
        routes, pkg = self.routes(**{
            "/git/trees/main": resp(200, {"truncated": False, "tree": [
                {"path": "web", "type": "tree"},
                {"path": "web/package.json", "type": "blob", "size": 50}]}),
            "/contents/web/package.json": resp(200, {"encoding": "base64", "content": self.PKG}),
        })
        with mock.patch("requests.get", side_effect=requests.ConnectionError("registry down")):
            code, out = run(["https://github.com/o/r"], routes)
        self.assertEqual(code, 0)
        self.assertIn("web/package.json", out)
        self.assertIn("left-pad", out)
        self.assertIn("unknown (lookup failed)", out)  # a failed lookup is never shown as up to date
        self.assertIn("Verdict: Not determinable", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
