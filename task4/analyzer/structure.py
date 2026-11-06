"""Section 2: file structure summary. Pure function of the bundle (no network)."""
from __future__ import annotations

from collections import Counter

TRUNC_NOTE = "GitHub truncated the tree (very large repo); counts are lower bounds"
TOP_LEVEL_LIMIT = 15


# Purpose notes come from a fixed name map only; unknown names are not guessed.
_DIR_PURPOSE = {
    "src": "source code", "lib": "library source", "app": "application code", "pkg": "packages",
    "cmd": "CLI entry points", "internal": "internal packages", "test": "tests", "tests": "tests",
    "spec": "tests", "__tests__": "tests", "docs": "documentation", "doc": "documentation",
    "examples": "example code", "example": "example code", "samples": "example code",
    "scripts": "helper scripts", "bin": "executables/scripts", "tools": "dev tooling",
    ".github": "GitHub config / CI workflows", "public": "static web assets", "static": "static assets",
    "assets": "assets (images, styles)", "frontend": "frontend app", "backend": "backend app",
    "client": "client app", "server": "server code", "api": "API code", "config": "configuration",
    "migrations": "database migrations", "benchmarks": "benchmarks", "benchmark": "benchmarks",
    "data": "data files", "notebooks": "Jupyter notebooks", "packages": "monorepo packages",
    ".vscode": "editor settings", "docker": "Docker files", "deploy": "deployment config",
}
_FILE_PURPOSE = {
    "readme": "project overview", "license": "license", "licence": "license",
    "contributing": "contribution guide", "changelog": "change log", "history": "change log",
    "package.json": "npm manifest", "requirements.txt": "Python dependencies",
    "pyproject.toml": "Python project config", "setup.py": "Python packaging",
    "dockerfile": "container build", "makefile": "build tasks", ".gitignore": "git ignore rules",
    "index.js": "JS entry point", "main.py": "Python entry point", "go.mod": "Go module",
    "cargo.toml": "Rust manifest", "pom.xml": "Maven build", "build.gradle": "Gradle build",
}


def purpose_of(name: str, is_dir: bool) -> str:
    low = name.lower()
    if is_dir:
        return _DIR_PURPOSE.get(low, "-")
    stem = low.rsplit(".", 1)[0] if low.rsplit(".", 1)[-1] in ("md", "txt", "rst") else low
    return _FILE_PURPOSE.get(low) or _FILE_PURPOSE.get(stem) or (
        "config/tooling" if low.startswith(".") else "-")


def _ext(path: str) -> str:
    base = path.rsplit("/", 1)[-1]
    if base.startswith(".") and base.count(".") == 1:
        return "(dotfile)"
    if "." not in base:
        return "(none)"
    return base.rsplit(".", 1)[-1].lower() or "(none)"


def _unavailable(reason: str, truncated: bool = False) -> dict:
    return {"status": "unavailable", "reason": reason, "total_files": 0, "total_dirs": 0,
            "max_depth": 0, "total_size_bytes": 0, "top_level": [], "top_level_more": 0,
            "top_extensions": [], "notable": [], "submodules": 0,
            "truncated": truncated, "note": None}


def summarize_structure(bundle: dict) -> dict:
    """Summarise bundle["tree"]; see STAGE_PROMPTS.md Stage 3 for the return shape."""
    tree = bundle.get("tree")
    truncated = bool(bundle.get("tree_truncated"))
    if tree is None:
        return _unavailable(bundle.get("tree_error") or "File tree not available", truncated)

    blobs = [e for e in tree if e.get("type") == "blob"]
    dirs = [e for e in tree if e.get("type") == "tree"]
    submodules = [e for e in tree if e.get("type") == "commit"]
    if not blobs:
        return _unavailable("Repository has no files on the default branch", truncated)

    blob_paths = [e.get("path", "") for e in blobs]
    dir_paths = {e.get("path", "") for e in dirs}

    total_size = sum(int(e.get("size") or 0) for e in blobs)
    max_depth = max(p.count("/") for p in blob_paths)

    # Top level: directories with the number of files beneath them, then root files.
    dir_counts: Counter = Counter()
    root_files: list[str] = []
    for p in blob_paths:
        if "/" in p:
            dir_counts[p.split("/", 1)[0]] += 1
        else:
            root_files.append(p)
    for d in dir_paths:  # top-level dirs holding only sub-dirs/submodules
        if "/" not in d and d not in dir_counts:
            dir_counts[d] = 0
    top_dirs = sorted(dir_counts.items(), key=lambda kv: (-kv[1], kv[0].lower()))
    top_level = [{"name": n, "type": "dir", "files": c, "purpose": purpose_of(n, True)} for n, c in top_dirs]
    top_level += [{"name": f, "type": "file", "files": 1, "purpose": purpose_of(f, False)}
                  for f in sorted(root_files, key=str.lower)]
    extra = max(0, len(top_level) - TOP_LEVEL_LIMIT)
    top_level = top_level[:TOP_LEVEL_LIMIT]

    ext_counts = Counter(_ext(p) for p in blob_paths)
    top_extensions = [{"ext": e, "count": c}
                      for e, c in sorted(ext_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:8]]

    notable: list[str] = []
    for f in sorted(root_files, key=str.lower):
        up = f.upper()
        if up.startswith("README") or up.startswith("LICENSE"):
            notable.append(f)
    for d in ("tests", "test", "docs"):
        if d in dir_counts:
            notable.append(d + "/")
    if ".github/workflows" in dir_paths or any(p.startswith(".github/workflows/") for p in blob_paths):
        notable.append(".github/workflows")
    if "Dockerfile" in root_files:
        notable.append("Dockerfile")

    notes = []
    if truncated:
        notes.append(TRUNC_NOTE)
    if extra:
        notes.append(f"+{extra} more top-level entries not shown")

    return {"status": "ok", "reason": None,
            "total_files": len(blobs), "total_dirs": len(dirs), "max_depth": max_depth,
            "total_size_bytes": total_size, "top_level": top_level, "top_level_more": extra,
            "top_extensions": top_extensions, "notable": notable,
            "submodules": len(submodules),
            "truncated": truncated, "note": "; ".join(notes) if notes else None}
