"""Contribution activity: weekly commits (last 52 weeks) + top contributors. Pure."""
from __future__ import annotations

from datetime import datetime, timezone

CHART_WEEKS = 12
TOP_N = 5
CONTRIBUTORS_LABEL = "all-time commits on the default branch (GitHub API, cached)"


def _weekly(bundle: dict) -> tuple[list[dict] | None, str | None]:
    """Return (sorted list of {"week": int, "total": int}, None) or (None, reason)."""
    raw = bundle.get("commit_activity")
    if raw is None:
        return None, bundle.get("activity_error") or "commit activity was not returned by GitHub"
    if not isinstance(raw, list) or not raw:
        return None, bundle.get("activity_error") or "GitHub returned no commit statistics"
    rows = []
    for w in raw:
        if not isinstance(w, dict):
            continue
        week, total = w.get("week"), w.get("total")
        if isinstance(week, (int, float)) and isinstance(total, int):
            rows.append({"week": int(week), "total": total})
    if not rows:
        return None, "GitHub commit statistics had an unexpected format"
    rows.sort(key=lambda r: r["week"])
    return rows, None


def _contributors(bundle: dict) -> tuple[list[dict], str | None]:
    raw = bundle.get("contributors")
    if raw is None:
        return [], bundle.get("contributors_error") or "contributor list was not returned by GitHub"
    if not isinstance(raw, list):
        return [], "contributor list had an unexpected format"
    people = [{"login": c["login"], "commits": c.get("contributions")}
              for c in raw
              if isinstance(c, dict) and c.get("login") and isinstance(c.get("contributions"), int)]
    if not people:
        return [], "GitHub returned no contributors"
    people.sort(key=lambda p: p["commits"], reverse=True)  # stable: keeps API order on ties
    return people[:TOP_N], None


def analyze_activity(bundle: dict) -> dict:
    bundle = bundle or {}
    weekly, weekly_reason = _weekly(bundle)
    top, contributors_reason = _contributors(bundle)

    if weekly is None and contributors_reason is not None:
        return {"status": "unavailable",
                "reason": f"weekly commits: {weekly_reason}; contributors: {contributors_reason}",
                "weeks": [], "total_52w": None, "active_weeks_52w": None,
                "top_contributors": [], "contributors_reason": contributors_reason,
                "contributors_label": CONTRIBUTORS_LABEL,
                "weekly_reason": weekly_reason, "note": None}

    note = None
    if weekly is None:
        weeks, total, active = [], None, None
        note = f"Not available: {weekly_reason}"
    else:
        weeks = [{"week_start": datetime.fromtimestamp(r["week"], timezone.utc).date().isoformat(),
                  "commits": r["total"]} for r in weekly[-CHART_WEEKS:]]
        total = sum(r["total"] for r in weekly)
        active = sum(1 for r in weekly if r["total"] > 0)
        if total == 0:
            note = "No commits in the last 52 weeks"

    return {"status": "ok", "reason": None,
            "weeks": weeks, "total_52w": total, "active_weeks_52w": active,
            "top_contributors": top, "contributors_reason": contributors_reason,
            "contributors_label": CONTRIBUTORS_LABEL,
            "weekly_reason": weekly_reason, "note": note}
