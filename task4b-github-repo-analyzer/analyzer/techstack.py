"""Section 1: tech stack detection with evidence. Pure function of the bundle (no network)."""
from __future__ import annotations

import json
import re

# package.json dependency name -> display name
NPM_FRAMEWORKS = {
    "react": "React", "next": "Next.js", "vue": "Vue", "@angular/core": "Angular",
    "svelte": "Svelte", "express": "Express", "koa": "Koa", "fastify": "Fastify",
    "@nestjs/core": "NestJS", "jest": "Jest", "mocha": "Mocha", "vitest": "Vitest",
    "typescript": "TypeScript", "webpack": "webpack", "vite": "Vite", "eslint": "ESLint",
}

# normalized PyPI name -> display name
PY_FRAMEWORKS = {
    "django": "Django", "flask": "Flask", "fastapi": "FastAPI", "numpy": "NumPy",
    "pandas": "pandas", "torch": "PyTorch", "tensorflow": "TensorFlow",
    "scikit-learn": "scikit-learn", "pytest": "pytest", "sqlalchemy": "SQLAlchemy",
    "requests": "Requests",
}

# root files whose presence (never content) indicates a build system / package manager
BUILD_FILES = [
    "pyproject.toml", "setup.py", "setup.cfg", "Pipfile", "poetry.lock", "package-lock.json",
    "yarn.lock", "pnpm-lock.yaml", "go.mod", "Cargo.toml", "pom.xml", "build.gradle", "Gemfile",
    "composer.json", "Makefile", "CMakeLists.txt",
]

# root files whose presence indicates a tool -> display name
TOOL_FILES = {
    ".travis.yml": "Travis CI", ".gitlab-ci.yml": "GitLab CI", "tox.ini": "tox",
    ".pre-commit-config.yaml": "pre-commit",
}

DOCKER_FILES = ("Dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml")

_REQ_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def _norm_py(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _language_items(bundle: dict, notes: list[str]) -> list[dict]:
    langs = bundle.get("languages")
    if not langs or not isinstance(langs, dict):
        err = bundle.get("languages_error") or "GitHub detected no languages"
        notes.append(f"language data unavailable: {err}")
        return []
    total = sum(v for v in langs.values() if isinstance(v, (int, float)))
    if total <= 0:
        notes.append("language data unavailable: GitHub reported 0 bytes of code")
        return []
    items = []
    for name, size in sorted(langs.items(), key=lambda kv: kv[1], reverse=True):
        pct = 100.0 * size / total
        if pct >= 1.0:
            items.append({"name": name, "category": "language",
                          "evidence": f"GitHub languages API: {pct:.1f}% of code bytes"})
    return items


def _package_json_items(text: str, notes: list[str]) -> list[dict]:
    try:
        data = json.loads(text)
    except (ValueError, TypeError) as e:
        notes.append(f"package.json could not be parsed: {e}")
        return []
    if not isinstance(data, dict):
        notes.append("package.json could not be parsed: top level is not an object")
        return []
    items, seen = [], set()
    for section in ("dependencies", "devDependencies"):
        deps = data.get(section)
        if not isinstance(deps, dict):
            continue
        for dep, spec in deps.items():
            display = NPM_FRAMEWORKS.get(dep)
            if display and display not in seen:
                seen.add(display)
                cat = "dev tool" if section == "devDependencies" else "framework"
                items.append({"name": display, "category": cat,
                              "evidence": f"package.json {section}: {dep} {spec}"})
    return items


def _requirements_items(text: str) -> list[dict]:
    items, seen = [], set()
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        m = _REQ_NAME.match(line)
        if not m:
            continue
        display = PY_FRAMEWORKS.get(_norm_py(m.group(1)))
        if display and display not in seen:
            seen.add(display)
            shown = line.split("#", 1)[0].strip()
            items.append({"name": display, "category": "framework",
                          "evidence": f"requirements.txt line {lineno}: {shown}"})
    return items


def _tree_items(bundle: dict, notes: list[str]) -> list[dict]:
    tree = bundle.get("tree")
    if tree is None:
        err = bundle.get("tree_error") or "file tree unavailable"
        notes.append(f"build/tool files not checked: {err}")
        return []
    blob_paths = {e.get("path", "") for e in tree if e.get("type") == "blob"}
    items: list[dict] = []
    for f in BUILD_FILES:
        if f in blob_paths:
            items.append({"name": f, "category": "build", "evidence": f"file present: {f}"})
    docker = [p for p in DOCKER_FILES if p in blob_paths]
    if docker:
        items.append({"name": "Docker", "category": "tool",
                      "evidence": "file present: " + ", ".join(docker)})
    workflows = sorted(p for p in blob_paths
                       if p.startswith(".github/workflows/") and p.count("/") == 2
                       and p.lower().endswith((".yml", ".yaml")))
    if workflows:
        n = len(workflows)
        plural = "s" if n != 1 else ""
        items.append({"name": "GitHub Actions", "category": "tool",
                      "evidence": f"{n} workflow file{plural} in .github/workflows/"})
    for f, display in TOOL_FILES.items():
        if f in blob_paths:
            items.append({"name": display, "category": "tool", "evidence": f"file present: {f}"})
    if bundle.get("tree_truncated"):
        notes.append("GitHub truncated the tree; some tooling files may be missed")
    return items


def detect_stack(bundle: dict) -> dict:
    """Return {"status","reason","items":[{"name","category","evidence"}],"notes":[str]}."""
    notes: list[str] = []
    items: list[dict] = []
    items += _language_items(bundle, notes)
    files = bundle.get("files") or {}
    for path in sorted(files, key=lambda p: (p.count("/"), p.lower())):
        text, base = files[path], path.rsplit("/", 1)[-1]
        if text is None:
            continue
        if base == "package.json":
            new = _package_json_items(text, notes)
        elif base == "requirements.txt":
            new = _requirements_items(text)
        else:
            continue
        for it in new:  # keep the first (shallowest) evidence per framework; show which file
            if it["name"] not in {i["name"] for i in items}:
                if path != base:
                    it["evidence"] = it["evidence"].replace(base, path, 1)
                items.append(it)
    items += _tree_items(bundle, notes)
    notes.append("Frameworks are detected from requirements.txt/package.json (root, or shallowest sub-folders) and known file names.")
    if not items:
        detail = "; ".join(n for n in notes if not n.startswith("Frameworks are detected"))
        reason = "No languages or known manifest/tooling files detected"
        return {"status": "unavailable",
                "reason": f"{reason} ({detail})" if detail else reason,
                "items": [], "notes": notes}
    return {"status": "ok", "reason": None, "items": items, "notes": notes}
