"""GitHub webhook receiver (stdlib only)."""
import hashlib
import hmac
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import config
import pipeline

PR_ACTIONS = {"opened", "synchronize", "reopened", "ready_for_review"}


def verify_signature(secret, body, header):
    if not header or not header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header)


def make_handler(dry_run=False):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code, obj):
            data = json.dumps(obj, default=str).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path.rstrip("/") == "/health":
                self._send(200, {"ok": True})
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self):
            if self.path.rstrip("/") != "/webhook":
                return self._send(404, {"error": "not found"})
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else b""
            secret = config.get("WEBHOOK_SECRET")
            if secret and not verify_signature(secret, body, self.headers.get("X-Hub-Signature-256")):
                print("[1/6 webhook] signature mismatch - rejected", flush=True)
                return self._send(401, {"error": "invalid signature"})
            try:
                payload = json.loads(body or b"")
                if not isinstance(payload, dict):
                    raise ValueError("payload is not an object")
            except ValueError:
                return self._send(400, {"error": "bad JSON"})
            event = self.headers.get("X-GitHub-Event", "")
            action = payload.get("action")
            if event == "push":
                try:
                    import autopilot
                    repo = payload["repository"]["full_name"]
                    ref = payload.get("ref", "")
                    if not ref.startswith("refs/heads/") or payload.get("deleted"):
                        return self._send(200, {"ignored": f"push {ref}"})
                    print(f"[1/6 webhook] push {repo} {ref}", flush=True)
                    result = autopilot.handle_push(repo, ref[len("refs/heads/"):], payload.get("after"),
                                                   dry_run=dry_run,
                                                   base=payload["repository"].get("default_branch"),
                                                   skip_if_pr_exists=True)
                except (KeyError, TypeError):
                    return self._send(400, {"error": "missing repository/ref"})
                except Exception as e:
                    return self._send(500, {"error": str(e)})
                return self._send(200, result)
            if event == "pull_request" and action == "opened":
                import autopilot
                if autopilot.AUTO_MARKER in ((payload.get("pull_request") or {}).get("body") or ""):
                    return self._send(200, {"ignored": "PR opened by ai-pr-reviewer; the push handler reviews it"})
            if event != "pull_request" or action not in PR_ACTIONS:
                return self._send(200, {"ignored": f"{event}/{action}"})
            try:
                repo = payload["repository"]["full_name"]
                number = payload.get("number") or payload["pull_request"]["number"]
                pr = payload.get("pull_request") or {}
                print(f"[1/6 webhook] {event}/{action} {repo}#{number} "
                      f"'{pr.get('title')}' branch={(pr.get('head') or {}).get('ref')}", flush=True)
            except (KeyError, TypeError):
                return self._send(400, {"error": "missing repository/number"})
            try:
                result = pipeline.review_pr(repo, int(number), dry_run=dry_run)
            except Exception as e:
                return self._send(500, {"error": str(e)})
            self._send(200, result)

        def log_message(self, fmt, *args):
            pass

    return Handler


def make_server(port=8000, dry_run=False, host="0.0.0.0"):
    return ThreadingHTTPServer((host, port), make_handler(dry_run))


def serve(port=8000, dry_run=False):
    srv = make_server(port, dry_run)
    print(f"Listening on http://0.0.0.0:{srv.server_address[1]}/webhook"
          f"{' (dry-run)' if dry_run else ''}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
