"""Dependency health for root requirements.txt / package.json.

Parsing is pure. The only network I/O is the registry lookup (PyPI JSON / npm
registry), done with plain ``requests.get`` and NO Authorization header, so the
GitHub token is never sent to third parties.
"""
from __future__ import annotations

import json
import re
from typing import Callable

import requests

CAP = 30
DEFINITION = (
    "Healthy = at least 80% of dependencies pinned to an exact version AND at least 80% of "
    "pinned dependencies on the latest release."
)
NO_MANIFEST = "No requirements.txt or package.json found (repo root or sub-folders)"
_UA = {"User-Agent": "rc3-repo-analyzer", "Accept": "application/json"}
_TIMEOUT = (5, 10)
_OTHER_MANIFESTS = ("pyproject.toml", "setup.py", "setup.cfg", "Pipfile")

# ---------------------------------------------------------------- helpers

_PIP_PIN = re.compile(r"^===?\s*([^,*\s]+)$")
_PIP_LINE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)\s*(\[[^\]]*\])?\s*(.*)$")
_NPM_PIN = re.compile(r"^=?v?\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?(\+[0-9A-Za-z.-]+)?$")
_NPM_TAG = re.compile(r"^[A-Za-z][\w.-]*$")
_VCS_PREFIXES = ("git+", "hg+", "svn+", "bzr+", "http://", "https://", "file:", ".", "/")
_SKIP_OPTS = ("-i", "--index-url", "--extra-index-url", "-f", "--find-links", "--trusted-host",
              "--no-binary", "--only-binary", "--pre", "--require-hashes", "--prefer-binary",
              "--no-index")
_NESTED_OPTS = ("-r", "--requirement", "-c", "--constraint")


def normalize_pypi(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _strip_v(v: str) -> str:
    return v.strip().lstrip("=").lstrip("v").strip()


def _opt_name(line: str) -> str:
    return re.split(r"[\s=]", line, maxsplit=1)[0]


def classify_spec(ecosystem: str, spec) -> str:
    """Return "pinned" | "range" | "unknown" for one version spec."""
    if not isinstance(spec, str):
        return "unknown"
    s = spec.strip()
    if ecosystem == "pypi":
        if _PIP_PIN.match(s):
            return "pinned"
        return "range"
    # npm
    low = s.lower()
    if low.startswith(("workspace:", "file:", "link:", "portal:", "npm:", "git+", "git:",
                       "github:", "gitlab:", "bitbucket:", "http://", "https://")):
        return "unknown"
    if "/" in s and not s.startswith("@"):
        return "unknown"
    if _NPM_PIN.match(s):
        return "pinned"
    return "range"  # ^ ~ > < || - x * partials, "", dist-tags like "latest"


# ---------------------------------------------------------------- parsers (pure)

def parse_requirements(text: str) -> tuple[list[dict], list[str]]:
    """Parse requirements.txt text. Returns (deps, notes)."""
    deps: list[dict] = []
    notes: list[str] = []
    # 1. join continuation lines, keeping the starting line number
    logical: list[tuple[int, str]] = []
    buf, start = "", None
    for i, raw in enumerate(text.splitlines(), 1):
        if start is None:
            start = i
        if raw.rstrip().endswith("\\"):
            buf += raw.rstrip()[:-1] + " "
            continue
        logical.append((start, buf + raw))
        buf, start = "", None
    if buf:
        logical.append((start or 0, buf))

    for lineno, line in logical:
        # 2. comments: '#' at start or preceded by whitespace
        line = re.sub(r"(^|\s)#.*$", "", line).strip()
        if not line:
            continue
        source = f"requirements.txt line {lineno}"
        if line.startswith("-"):
            opt = _opt_name(line)
            if opt in _NESTED_OPTS or opt.startswith(("--requirement=", "--constraint=")):
                target = line[len(opt):].strip().lstrip("=").strip() or "?"
                notes.append(f"nested file {target} not followed")
            elif opt in ("-e", "--editable"):
                pass  # editable installs are not counted
            elif opt in _SKIP_OPTS or opt.split("=")[0] in _SKIP_OPTS:
                pass
            else:
                notes.append(f"option line skipped: {opt}")
            continue
        # 6. VCS / URL / local path / PEP 508 direct reference
        if line.startswith(_VCS_PREFIXES) or " @ " in line:
            name = line
            if " @ " in line:
                name = line.split(" @ ", 1)[0].strip()
            elif "#egg=" in line:
                name = line.split("#egg=", 1)[1].split("&")[0].strip()
            deps.append({"ecosystem": "pypi", "name": name, "lookup_name": None,
                         "spec": line, "kind": "unknown", "version": None, "source": source})
            continue
        # 7. per-requirement options
        for cut in (" --hash", " --global-option", " --install-option", " --config-settings"):
            if cut in line:
                line = line.split(cut, 1)[0].strip()
        # 8. environment markers
        marker = None
        if ";" in line:
            line, marker = (p.strip() for p in line.split(";", 1))
        m = _PIP_LINE.match(line)
        if not m:
            deps.append({"ecosystem": "pypi", "name": line, "lookup_name": None, "spec": line,
                         "kind": "unknown", "version": None, "source": source})
            continue
        name, spec = m.group(1), m.group(3).strip()
        kind = classify_spec("pypi", spec)
        pm = _PIP_PIN.match(spec)
        deps.append({"ecosystem": "pypi", "name": name, "lookup_name": normalize_pypi(name),
                     "spec": spec or "any", "kind": kind,
                     "version": pm.group(1) if pm else None, "source": source,
                     "marker": marker})
    return _dedupe(deps, notes)


def parse_package_json(text: str) -> tuple[list[dict], list[str]]:
    """Parse package.json text. Raises ValueError on invalid JSON / wrong shape."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"package.json is not valid JSON: {e}") from None
    if not isinstance(data, dict):
        raise ValueError("package.json is not valid JSON: top level is not an object")
    deps: list[dict] = []
    notes: list[str] = []
    for key, kind_label in (("dependencies", "prod"), ("devDependencies", "dev")):
        block = data.get(key) or {}
        if not isinstance(block, dict):
            notes.append(f"package.json {key} is not an object; skipped")
            continue
        for name, spec in block.items():
            kind = classify_spec("npm", spec)
            spec_s = spec.strip() if isinstance(spec, str) else repr(spec)
            lookup = name.replace("/", "%2F", 1) if name.startswith("@") else name
            deps.append({"ecosystem": "npm", "name": name,
                         "lookup_name": lookup if kind != "unknown" else None,
                         "spec": spec_s if spec_s else "any", "kind": kind,
                         "version": _strip_v(spec_s) if kind == "pinned" else None,
                         "source": f"package.json {key}", "dep_type": kind_label})
    return _dedupe(deps, notes)


def _dedupe(deps: list[dict], notes: list[str]) -> tuple[list[dict], list[str]]:
    seen: set[tuple[str, str]] = set()
    out = []
    for d in deps:
        key = (d["ecosystem"], d["lookup_name"] or d["name"].lower())
        if key in seen:
            notes.append(f"duplicate {d['name']} ignored ({d['source']})")
            continue
        seen.add(key)
        out.append(d)
    return out, notes


# ---------------------------------------------------------------- registry lookup

def registry_lookup(ecosystem: str, lookup_name: str) -> tuple[str | None, str | None]:
    """Return (latest_version, None) or (None, reason). No GitHub token is ever sent."""
    if ecosystem == "pypi":
        url, label = f"https://pypi.org/pypi/{lookup_name}/json", "PyPI"
    else:
        url, label = f"https://registry.npmjs.org/{lookup_name}/latest", "npm"
    try:
        r = requests.get(url, headers=_UA, timeout=_TIMEOUT)
    except requests.RequestException as e:
        return None, f"{label} registry error: {type(e).__name__}"
    if r.status_code == 404:
        return None, f"not found on {label}"
    if r.status_code != 200:
        return None, f"{label} registry error: HTTP {r.status_code}"
    try:
        data = r.json()
        version = data["info"]["version"] if ecosystem == "pypi" else data["version"]
    except (ValueError, KeyError, TypeError):
        return None, f"{label} response had no version field"
    if not isinstance(version, str) or not version.strip():
        return None, f"{label} response had no version field"
    return version.strip(), None


def compare_versions(a: str, b: str) -> int | None:
    """-1/0/1 comparing a to b; None if either is unparsable (used only for notes)."""
    ka, kb = _key(a), _key(b)
    if ka is None or kb is None:
        return None
    return (ka > kb) - (ka < kb)


def _key(v: str):
    v = _strip_v(v).split("+", 1)[0]
    m = re.match(r"^(\d+(?:\.\d+)*)(.*)$", v)
    if not m:
        return None
    core = tuple(int(x) for x in m.group(1).split("."))
    core = (core + (0, 0, 0))[:max(3, len(core))]
    pre = m.group(2).lstrip("-.")
    return core, 0 if pre else 1, pre


# ---------------------------------------------------------------- section

def _pct(n: int, d: int) -> float:
    return round(100.0 * n / d, 1) if d else 0.0


def analyze_deps(bundle: dict, lookup: Callable | None = None, cap: int = CAP) -> dict:
    lookup = lookup or registry_lookup
    files = (bundle or {}).get("files") or {}
    notes: list[str] = []
    manifests: list[str] = []
    all_deps: list[dict] = []
    problems: list[str] = []

    parsers = {"requirements.txt": parse_requirements, "package.json": parse_package_json}
    # Root manifests first, then nested ones (e.g. frontend/package.json).
    for path in sorted(files, key=lambda p: (p.count("/"), p.lower())):
        parser = parsers.get(path.rsplit("/", 1)[-1])
        if parser is None:
            continue
        text = files[path]
        if not isinstance(text, str):
            problems.append(f"{path} could not be read (larger than 1 MB or not text)")
            continue
        try:
            deps, n = parser(text)
        except ValueError as e:
            problems.append(str(e))
            continue
        manifests.append(path)
        all_deps.extend(deps)
        notes.extend(n)

    if not manifests:
        if problems:
            return _unavailable("; ".join(problems))
        reason = NO_MANIFEST
        tree = (bundle or {}).get("tree") or []
        others = sorted({t.get("path") for t in tree if isinstance(t, dict)
                         and t.get("path") in _OTHER_MANIFESTS})
        if others:
            reason += f" (found: {', '.join(others)} - not parsed)"
        return _unavailable(reason)
    notes.extend(problems)

    total = len(all_deps)
    if total == 0:
        notes.insert(0, "Not applicable: manifest declares no dependencies")
        return {"status": "ok", "reason": None, "manifests": manifests, "deps": [],
                "pinned_pct": 0.0, "uptodate_pct_of_pinned": 0.0, "healthy": None,
                "definition": DEFINITION, "note": "; ".join(notes)}

    # lookup order: pinned first, then ranges; unparsable never looked up
    pinned = [d for d in all_deps if d["kind"] == "pinned"]
    ranged = [d for d in all_deps if d["kind"] == "range"]
    eligible = pinned + ranged
    to_check = eligible[:cap]
    checked_ids = {id(d) for d in to_check}
    cache: dict[tuple[str, str], tuple[str | None, str | None]] = {}
    for d in to_check:
        k = (d["ecosystem"], d["lookup_name"])
        if k not in cache:
            try:
                cache[k] = lookup(*k)
            except Exception as e:  # a custom lookup must never crash the report
                cache[k] = (None, f"lookup error: {type(e).__name__}")

    rows = []
    up_to_date = pinned_ok = 0
    for d in all_deps:
        latest, why = None, None
        if d["kind"] == "unknown":
            state = "unknown (unparsable)"
        elif id(d) not in checked_ids:
            state = "unknown (range)" if d["kind"] == "range" else "unknown (lookup failed)"
            why = f"not checked: {cap}-lookup cap reached"
        else:
            latest, why = cache[(d["ecosystem"], d["lookup_name"])]
            if d["kind"] == "range":
                state = "unknown (range)"
            elif latest is None:
                state = "unknown (lookup failed)"
            else:
                pinned_ok += 1
                if _strip_v(d["version"]) == _strip_v(latest):
                    state = "up-to-date"
                    up_to_date += 1
                else:
                    state = "outdated"
        row = {"name": d["name"], "ecosystem": d["ecosystem"], "spec": d["spec"],
               "pinned": d["kind"] == "pinned", "latest": latest, "state": state,
               "source": d["source"]}
        if why:
            row["reason"] = why
        rows.append(row)

    n_pinned = len(pinned)
    pinned_pct = _pct(n_pinned, total)
    uptodate_pct = _pct(up_to_date, pinned_ok)

    # cap / coverage notes
    if len(eligible) > cap:
        notes.insert(0, f"Checked {cap} of {len(eligible)}; pinned checked first")
    else:
        notes.insert(0, f"Checked {len(to_check)} of {len(eligible)} registry lookups")
    if n_pinned > cap:
        notes.append(f"up-to-date share based on {min(cap, n_pinned)} of {n_pinned} pinned")
    failed_pinned = sum(1 for r in rows if r["pinned"] and r["state"] == "unknown (lookup failed)"
                        and "cap" not in r.get("reason", ""))
    if failed_pinned:
        notes.append(f"{failed_pinned} pinned lookup(s) failed and are excluded from the up-to-date share")

    if n_pinned == 0:
        healthy = False
        notes.append("no pinned dependencies")
    elif pinned_pct < 80:
        healthy = False
    elif pinned_ok == 0:
        healthy = None
        notes.append("Not determinable: no pinned dependency version could be checked against the registry")
    else:
        healthy = uptodate_pct >= 80

    return {"status": "ok", "reason": None, "manifests": manifests, "deps": rows,
            "pinned_pct": pinned_pct, "uptodate_pct_of_pinned": uptodate_pct,
            "healthy": healthy, "definition": DEFINITION, "note": "; ".join(notes) or None}


def _unavailable(reason: str) -> dict:
    return {"status": "unavailable", "reason": reason, "manifests": [], "deps": [],
            "pinned_pct": 0.0, "uptodate_pct_of_pinned": 0.0, "healthy": None,
            "definition": DEFINITION, "note": None}
