"""Section 3: structural complexity score (0-100). Pure function of the bundle (no network)."""
from __future__ import annotations

import math

LARGE_BYTES = 102_400  # 100 KB

FORMULA = (
    "score = size + depth + large_files + lang_spread (0-25 each, 0-100)\n"
    "  size        = 25*min(1, log10(files)/4)       [10,000+ files = 25]\n"
    "  depth       = 25*min(1, max_depth/10)         [depth 10+ = 25]\n"
    "  large_files = 25*min(1, share>100KB / 0.10)   [10%+ large = 25]\n"
    "  lang_spread = 25*min(1, (langs>=1% - 1)/5)    [6+ langs = 25]\n"
    "Bands: <25 Low, 25-<50 Moderate, 50-<75 High, >=75 Very high."
)

CAVEAT = ("Heuristic based on file count, nesting, file sizes and language bytes from the GitHub API; "
          "it does not measure lines of code or cyclomatic complexity.")


def _clamp1(x: float) -> float:
    return min(1.0, max(0.0, x))


def band_for(score: float) -> str:
    """Half-open bands: <25 Low, 25<=s<50 Moderate, 50<=s<75 High, >=75 Very high."""
    if score < 25:
        return "Low"
    if score < 50:
        return "Moderate"
    if score < 75:
        return "High"
    return "Very high"


def _component(name: str, value: str, raw: float) -> dict:
    return {"name": name, "value": value, "raw": round(raw, 4),
            "points": round(25 * _clamp1(raw), 2), "max": 25}


def score_complexity(bundle: dict) -> dict:
    """Return {"status","reason","score","band","components","formula","caveat","notes","note"}."""
    empty = {"score": None, "band": None, "components": [], "formula": FORMULA,
             "caveat": CAVEAT, "notes": [], "note": None}
    tree = bundle.get("tree")
    if tree is None:
        reason = bundle.get("tree_error") or "file tree not available"
        return {"status": "unavailable", "reason": f"Needs the file tree: {reason}", **empty}
    blobs = [e for e in tree if e.get("type") == "blob"]
    if not blobs:
        return {"status": "unavailable",
                "reason": "Needs the file tree: Repository has no files on the default branch", **empty}

    notes: list[str] = []
    files = len(blobs)
    max_depth = max(e.get("path", "").count("/") for e in blobs)
    large = sum(1 for e in blobs if int(e.get("size") or 0) > LARGE_BYTES)
    share = large / files

    langs = bundle.get("languages")
    nums = [v for v in langs.values() if isinstance(v, (int, float))] if isinstance(langs, dict) else []
    total_bytes = sum(nums)
    if total_bytes > 0:
        n_langs = sum(1 for v in nums if 100.0 * v / total_bytes >= 1.0)
        spread_raw = (n_langs - 1) / 5
        plural = "s" if n_langs != 1 else ""
        spread_value = f"{n_langs} language{plural} >=1% of bytes"
    else:
        spread_raw = 0.0
        spread_value = "language data unavailable"
        err = bundle.get("languages_error")
        if err and err != "GitHub detected no languages":
            # API failure, not a genuinely empty result: say so, the 0 points are not a measurement.
            notes.append(f"language data unavailable ({err}); language_spread counted as 0, "
                         "so the score is a lower bound")
        else:
            notes.append("language data unavailable")

    components = [
        _component("size", f"{files:,} files", math.log10(max(files, 1)) / 4),
        _component("depth", f"max depth {max_depth}", max_depth / 10),
        _component("large_files", f"{large:,} of {files:,} files >100 KB ({100 * share:.1f}%)", share / 0.10),
        _component("language_spread", spread_value, spread_raw),
    ]
    score = round(sum(c["points"] for c in components), 1)
    if bundle.get("tree_truncated"):
        notes.append("GitHub truncated the tree (very large repo); score is a lower bound")

    return {"status": "ok", "reason": None, "score": score, "band": band_for(score),
            "components": components, "formula": FORMULA, "caveat": CAVEAT,
            "notes": notes, "note": "; ".join(notes) if notes else None}
