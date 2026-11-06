"""Rendering only: turns the section dicts into a rich terminal report.

This module never computes analysis numbers and never touches the network. Every value shown
comes from the section dicts (or the raw /repos JSON passed as ``repo_meta``). Anything a
section could not determine is printed as ``Not available: <reason>``.
"""

from __future__ import annotations

from datetime import datetime, timezone

from rich import box
from rich.console import Console, Group
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

BAR_WIDTH = 40
_BLOCKS = " ▏▎▍▌▋▊▉█"

SECTION_ORDER = [
    ("techstack", "1. Tech Stack"),
    ("structure", "2. File Structure"),
    ("complexity", "3. Code Complexity"),
    ("deps", "4. Dependency Health"),
    ("activity", "5. Contribution Activity"),
]

COMPLEXITY_BANDS = "Bands: <25 Low | 25-50 Moderate | 50-75 High | 75+ Very high"
DEFAULT_HEALTHY_DEFINITION = (
    "Healthy = at least 80% of dependencies pinned to an exact version AND at least 80% of "
    "pinned dependencies on the latest release."
)


# --------------------------------------------------------------------------- helpers

def _s(value) -> str:
    """Escape any API-provided text so rich does not interpret [brackets] as markup."""
    return escape(str(value))


def _na(reason) -> Text:
    reason = reason if reason else "no reason given"
    return Text(f"Not available: {reason}", style="yellow")


def _fmt_int(value) -> str:
    if isinstance(value, bool) or value is None:
        return "Not available"
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        return f"{value:,.1f}"
    return _s(value)


def _fmt_bytes(n) -> str:
    if not isinstance(n, (int, float)) or isinstance(n, bool):
        return "Not available"
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{int(size)} B" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{n} B"


def _fmt_pct(value) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{value:.1f}%"
    return "n/a"


def bar(value, vmax, width: int = BAR_WIDTH) -> str:
    """Hand-drawn horizontal bar using eighth-block characters, padded to ``width``.

    A non-zero value always shows at least one thin block so it never looks like zero.
    """
    try:
        v = max(0.0, float(value))
        m = float(vmax)
    except (TypeError, ValueError):
        return " " * width
    if m <= 0 or v <= 0:
        return " " * width
    units = int(round(v / m * width * 8))
    units = max(units, 1)
    full, rem = divmod(units, 8)
    out = "█" * full
    if rem:
        out += _BLOCKS[rem]
    return out[:width].ljust(width)


def _notes_renderables(section: dict) -> list:
    """Collect a section's free-text notes (``note`` str and/or ``notes`` list)."""
    out, seen = [], set()
    notes = section.get("notes")
    notes = list(notes) if isinstance(notes, (list, tuple)) else []
    note = section.get("note")
    if note and str(note) != "; ".join(str(n) for n in notes if n):
        notes.insert(0, note)
    for n in notes:
        if n and str(n) not in seen:
            seen.add(str(n))
            out.append(Text(f"Note: {n}", style="dim"))
    return out


def _unavailable_panel(title: str, reason) -> Panel:
    return Panel(_na(reason), title=title, title_align="left", border_style="yellow")


def _is_ok(section) -> bool:
    return isinstance(section, dict) and section.get("status") == "ok"


def _reason_of(section) -> str:
    if not isinstance(section, dict):
        return "section returned no data"
    return section.get("reason") or "no reason given"


# --------------------------------------------------------------------------- header / footer

def _header(repo_meta: dict, token_used: bool) -> Panel:
    repo_meta = repo_meta or {}
    full_name = repo_meta.get("full_name") or "Not available"
    desc = repo_meta.get("description")
    desc_line = Text(desc) if desc else Text("Description: Not available: no description set on GitHub", style="dim")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    branch = repo_meta.get("default_branch") or "Not available"
    meta = Text.assemble(
        ("Stars ", "bold"), _fmt_int(repo_meta.get("stargazers_count")),
        ("   Forks ", "bold"), _fmt_int(repo_meta.get("forks_count")),
        ("   Default branch ", "bold"), str(branch),
        ("   Analysed ", "bold"), now,
        ("   Authenticated ", "bold"), ("yes" if token_used else "no"),
    )
    return Panel(
        Group(desc_line, meta),
        title=f"Repository Analysis: {_s(full_name)}",
        border_style="cyan",
    )


def _reset_hhmm(epoch) -> str:
    try:
        return datetime.fromtimestamp(int(epoch), timezone.utc).strftime("%H:%M UTC")
    except (TypeError, ValueError, OverflowError, OSError):
        return "?"


def _footer(token_used: bool, rate: dict | None, api_calls) -> Text:
    rate = rate or {}
    remaining = rate.get("remaining")
    limit = rate.get("limit")
    reset = rate.get("reset_epoch")
    rem_s = "?" if remaining is None else str(remaining)
    lim_s = "?" if limit is None else str(limit)
    calls_s = "?" if api_calls is None else str(api_calls)
    token_s = (
        "yes (authenticated, 5,000 requests/hour)" if token_used
        else "no (unauthenticated, 60 requests/hour; set GITHUB_TOKEN for 5,000)"
    )
    return Text(
        f"GitHub API calls: {calls_s} | rate limit remaining: {rem_s}/{lim_s} "
        f"(resets {_reset_hhmm(reset) if reset is not None else '?'}) | token used: {token_s}",
        style="dim",
    )


# --------------------------------------------------------------------------- sections

def _render_techstack(sec: dict, title: str) -> Panel:
    items = sec.get("items") or []
    table = Table(box=box.SIMPLE_HEAVY, expand=False)
    table.add_column("Name", style="bold")
    table.add_column("Category")
    table.add_column("Evidence")
    order = {"language": 0, "framework": 1, "build": 2, "tool": 3}
    for it in sorted(items, key=lambda i: order.get(i.get("category"), 9)):
        table.add_row(_s(it.get("name", "?")), _s(it.get("category", "?")), _s(it.get("evidence", "")))
    body = [table] if items else [_na("no items detected")]
    body += _notes_renderables(sec)
    return Panel(Group(*body), title=title, title_align="left", border_style="green")


def _render_structure(sec: dict, title: str) -> Panel:
    body = []
    summary = Text.assemble(
        (_fmt_int(sec.get("total_files")), "bold"), " files | ",
        (_fmt_int(sec.get("total_dirs")), "bold"), " dirs | max depth ",
        (_fmt_int(sec.get("max_depth")), "bold"), " | total size ",
        (_fmt_bytes(sec.get("total_size_bytes")), "bold"),
    )
    body.append(summary)

    top = sec.get("top_level") or []
    if top:
        t = Table(title="Top level", box=box.SIMPLE_HEAVY, title_justify="left")
        t.add_column("Entry")
        t.add_column("Kind")
        t.add_column("Files", justify="right")
        t.add_column("Purpose (from name; - = not determined)")
        for e in top:
            kind = e.get("type", "?")
            name = e.get("name", "?")
            if kind == "dir" and not str(name).endswith("/"):
                name = f"{name}/"
            t.add_row(_s(name), _s(kind), _fmt_int(e.get("files")), _s(e.get("purpose") or "-"))
        body.append(t)

    exts = sec.get("top_extensions") or []
    if exts:
        t = Table(title="Top extensions", box=box.SIMPLE_HEAVY, title_justify="left")
        t.add_column("Extension")
        t.add_column("Files", justify="right")
        for e in exts:
            t.add_row(_s(e.get("ext", "?")), _fmt_int(e.get("count")))
        body.append(t)

    largest = sec.get("largest_files") or []
    if largest:
        t = Table(title="Largest files", box=box.SIMPLE_HEAVY, title_justify="left")
        t.add_column("Path")
        t.add_column("Size", justify="right")
        for e in largest:
            t.add_row(_s(e.get("path", "?")), _fmt_bytes(e.get("size")))
        body.append(t)

    notable = sec.get("notable")
    if notable:
        body.append(Text("Key files/dirs present: " + ", ".join(str(n) for n in notable)))
    elif notable is not None:
        body.append(Text("Key files/dirs present: none of README, LICENSE, tests/, docs/, CI workflows, Dockerfile", style="dim"))

    if sec.get("truncated"):
        body.append(Text("Warning: GitHub truncated the tree; counts are lower bounds.", style="yellow"))
    body += _notes_renderables(sec)
    return Panel(Group(*body), title=title, title_align="left", border_style="green")


def _render_complexity(sec: dict, title: str) -> Panel:
    score = sec.get("score")
    band = sec.get("band") or "?"
    score_s = f"{score:.1f}" if isinstance(score, (int, float)) and not isinstance(score, bool) else "?"
    full_title = f"{title}: {score_s} / 100 ({_s(band)})"

    t = Table(box=box.SIMPLE_HEAVY)
    t.add_column("Component")
    t.add_column("Measured")
    t.add_column("Points", justify="right")
    for c in sec.get("components") or []:
        pts = c.get("points")
        pts_s = f"{pts:.2f}" if isinstance(pts, (int, float)) and not isinstance(pts, bool) else "?"
        t.add_row(_s(c.get("name", "?")), _s(c.get("value", "")), f"{pts_s} / {c.get('max', 25)}")
    body = [t]
    if sec.get("formula"):
        body.append(Text("Formula:\n" + str(sec["formula"])))
    else:
        body.append(Text(COMPLEXITY_BANDS))
    if sec.get("caveat"):
        body.append(Text("Caveat: " + str(sec["caveat"]), style="italic"))
    body += _notes_renderables(sec)
    return Panel(Group(*body), title=full_title, title_align="left", border_style="green")


_STATE_STYLE = {"up-to-date": "green", "outdated": "red"}


def _render_deps(sec: dict, title: str) -> Panel:
    healthy = sec.get("healthy")
    if healthy is True:
        verdict, style = "Healthy", "green"
    elif healthy is False:
        verdict, style = "Not healthy", "red"
    elif sec.get("deps"):
        verdict, style = "Not determinable", "yellow"
    else:
        verdict, style = "Not applicable", "yellow"
    full_title = f"{title}: {verdict}"

    deps = sec.get("deps") or []
    pinned = sum(1 for d in deps if d.get("pinned"))
    pinned_checked = sum(1 for d in deps if d.get("pinned") and d.get("latest"))
    uptodate_s = (_fmt_pct(sec.get("uptodate_pct_of_pinned")) if pinned_checked
                  else "Not available: no pinned dependency could be checked")
    body = [
        Text("Definition: " + str(sec.get("definition") or DEFAULT_HEALTHY_DEFINITION), style="italic"),
        Text(
            f"Manifests: {', '.join(sec.get('manifests') or []) or 'none'} | {len(deps)} deps | "
            f"{pinned} pinned ({_fmt_pct(sec.get('pinned_pct'))}) | "
            f"up to date (of pinned with a successful lookup): {uptodate_s}"
        ),
    ]
    if deps:
        multi_eco = len({d.get("ecosystem") for d in deps}) > 1
        t = Table(box=box.SIMPLE_HEAVY, pad_edge=False)
        t.add_column("Package", overflow="fold")
        if multi_eco:
            t.add_column("Eco", no_wrap=True)
        t.add_column("Spec", overflow="fold")
        t.add_column("Latest", overflow="fold")
        t.add_column("State", no_wrap=True)
        for d in deps:
            state = str(d.get("state", "?"))
            st_style = _STATE_STYLE.get(state, "yellow")
            if d.get("latest"):
                latest = _s(d.get("latest"))
            elif "cap" in str(d.get("reason") or ""):
                latest = "not checked (cap)"
            elif d.get("reason"):
                latest = _s(d.get("reason"))
            else:
                latest = "-"
            row = [_s(d.get("name", "?"))]
            if multi_eco:
                row.append(_s(d.get("ecosystem", "?")))
            row += [_s(d.get("spec") or "any"), latest, Text(state, style=st_style)]
            t.add_row(*row)
        body.append(Text("State: up-to-date/outdated only for pinned deps; ranges are never judged.", style="dim"))
        body.append(t)
    body.append(Text(f"Verdict: {verdict}", style=f"bold {style}"))
    body += _notes_renderables(sec)
    border = "green" if healthy is True else ("red" if healthy is False else "yellow")
    return Panel(Group(*body), title=full_title, title_align="left", border_style=border)


def _weekly_unavailable_reason(sec: dict) -> str:
    for key in ("weekly_reason", "weeks_reason", "activity_reason", "activity_error"):
        if sec.get(key):
            return str(sec[key])
    if sec.get("reason"):
        return str(sec["reason"])
    if sec.get("note"):
        return str(sec["note"])
    return "no weekly commit data returned by GitHub"


def _render_activity(sec: dict, title: str) -> Panel:
    body = []
    weeks = sec.get("weeks") or []
    shown_note = False
    if weeks:
        body.append(Text(
            f"{_fmt_int(sec.get('total_52w'))} commits in the last 52 weeks | "
            f"{_fmt_int(sec.get('active_weeks_52w'))} active weeks (default branch, GitHub stats API)"
        ))
        body.append(Text(f"Commits per week (last {len(weeks)} weeks):", style="bold"))
        values = [w.get("commits") or 0 for w in weeks]
        vmax = max(values) if values else 0
        lines = Text()
        for w, v in zip(weeks, values):
            lines.append(f"{w.get('week_start', '?')} │", style="dim")
            lines.append(bar(v, vmax), style="cyan")
            lines.append(f" {v}\n")
        lines.rstrip()
        body.append(lines)
        if vmax == 0 and not sec.get("note"):
            total52 = sec.get("total_52w") or 0
            msg = (f"No commits in the last {len(weeks)} weeks shown "
                   f"({total52} earlier in the 52-week window)." if total52
                   else "No commits in the last 52 weeks.")
            body.append(Text(msg, style="yellow"))
    else:
        reason = _weekly_unavailable_reason(sec)
        if sec.get("note") and str(sec.get("note")).endswith(reason):
            shown_note = True
        body.append(Text.assemble(("Weekly commits: ", "bold"), _na(reason)))

    contributors = sec.get("top_contributors") or []
    if contributors:
        body.append(Text(f"Top {len(contributors)} contributors (all-time commits, GitHub API):", style="bold"))
        cmax = max((c.get("commits") or 0) for c in contributors)
        width = max(len(str(c.get("login", "?"))) for c in contributors)
        lines = Text()
        for c in contributors:
            n = c.get("commits") or 0
            lines.append(f"{str(c.get('login', '?')).ljust(width)} │", style="dim")
            lines.append(bar(n, cmax, 30), style="magenta")
            lines.append(f" {n:,}\n")
        lines.rstrip()
        body.append(lines)
    else:
        body.append(Text.assemble(
            ("Top contributors: ", "bold"),
            _na(sec.get("contributors_reason") or "no contributor data returned by GitHub"),
        ))

    if not shown_note:
        body += _notes_renderables(sec)
    else:
        notes = sec.get("notes")
        if isinstance(notes, (list, tuple)):
            body += [Text(f"Note: {n}", style="dim") for n in notes if n]
    return Panel(Group(*body), title=title + " (default branch)", title_align="left", border_style="green")


_RENDERERS = {
    "techstack": _render_techstack,
    "structure": _render_structure,
    "complexity": _render_complexity,
    "deps": _render_deps,
    "activity": _render_activity,
}


# --------------------------------------------------------------------------- public API

def render(
    console: Console,
    repo_meta: dict,
    sections: dict,
    token_used: bool,
    rate: dict | None = None,
    api_calls: int | None = None,
) -> None:
    """Print the full report.

    sections: {"techstack", "structure", "complexity", "deps", "activity"} -> section dicts.
    rate (optional): client.rate = {"remaining", "limit", "reset_epoch"}; api_calls (optional): client.calls.
    Missing optional values print as "?" in the footer.
    """
    sections = sections or {}
    console.print(_header(repo_meta, token_used))

    unavailable = []
    for key, title in SECTION_ORDER:
        sec = sections.get(key)
        if not _is_ok(sec):
            reason = _reason_of(sec)
            unavailable.append((title, reason))
            console.print(_unavailable_panel(title, reason))
            continue
        try:
            console.print(_RENDERERS[key](sec, title))
        except Exception as exc:  # a rendering bug must not kill the whole report
            reason = f"internal rendering error: {exc}"
            unavailable.append((title, reason))
            console.print(_unavailable_panel(title, reason))

    if unavailable:
        console.print(Text("Unavailable sections:", style="bold yellow"))
        for title, reason in unavailable:
            console.print(Text(f"  {title}: Not available: {reason}", style="yellow"))

    console.print(_footer(token_used, rate, api_calls))
