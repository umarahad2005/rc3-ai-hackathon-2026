"""Convert tickets given in any common format into Jira issue JSON (REST v2 shape).

Drop files into tickets/inbox/ (.txt .md .pdf .docx .json .csv) and run:
    python cli.py import-tickets [--inbox tickets/inbox] [--out tickets/jira]
Each ticket becomes tickets/jira/<KEY>.json:
    {"key": KEY, "fields": {"summary": ..., "description": "...h3. Acceptance Criteria\n* ...", "labels": [KEY]}}
That is the same shape as GET /rest/api/2/issue/<KEY>, so story_fetcher reads it with JIRA_TICKETS_DIR.

Nothing is invented: when the file has no acceptance criteria, the JSON has none, and the
reviewer will then refuse to merge. When no ticket key is found, the file is skipped and reported.
"""
import csv
import html
import json
import os
import re
import zipfile

KEY_RE = re.compile(r"\b([A-Z][A-Z0-9]+-\d+)\b")
AC_HEAD_RE = re.compile(r"^\s*(?:h\d\.\s*|#+\s*)?acceptance\s+criteria\s*:?\s*$", re.I)
HEAD_RE = re.compile(r"^\s*(?:h\d\.\s*.+|#+\s+.+|[A-Z][A-Za-z /]{2,40}:\s*)$")
BULLET_RE = re.compile(r"^\s*(?:[*\-•●▪]|\d+[.)]|\[\s?[xX ]?\s?\])\s+(?:[☐☑☒✓✔]\s*)?(.*)$")
FIELD_RE = re.compile(r"^\s*(key|ticket|id|summary|title)\s*[:=]\s*(.+)$", re.I)


# ---------- text extraction ----------
def _read_docx(path):
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8", "ignore")
    paras = re.findall(r"<w:p[ >].*?</w:p>", xml, re.S)
    lines = []
    for p in paras:
        text = html.unescape("".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", p)))
        if "<w:numPr>" in p and text.strip():
            text = "* " + text  # Word list item -> bullet
        elif re.search(r'<w:pStyle w:val="(?:Heading|Title)', p) and text.strip():
            text = "## " + text  # Word heading -> ends the acceptance-criteria section
        lines.append(text)
    return "\n".join(lines)


def _read_pdf(path):
    from pypdf import PdfReader
    return "\n".join((page.extract_text() or "") for page in PdfReader(path).pages)


def read_text(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".docx":
        return _read_docx(path)
    if ext == ".pdf":
        return _read_pdf(path)
    with open(path, encoding="utf-8-sig", errors="replace") as f:
        return f.read()


# ---------- parsing ----------
def parse_ticket_text(text, fallback_key=None):
    """Return {"key","summary","description_text","acceptance_criteria":[...]} or None if no key."""
    lines = [ln.rstrip() for ln in text.replace("\r", "").split("\n")]
    key = summary = None
    for ln in lines:
        m = FIELD_RE.match(ln)
        if m:
            name, val = m.group(1).lower(), m.group(2).strip()
            if name in ("key", "ticket", "id") and not key and KEY_RE.search(val):
                key = KEY_RE.search(val).group(1)
            elif name in ("summary", "title") and not summary:
                summary = val
    if not key:
        m = KEY_RE.search(text)
        key = m.group(1) if m else fallback_key
    if not key:
        return None

    ac, desc, in_ac = [], [], False
    for ln in lines:
        if AC_HEAD_RE.match(ln):
            in_ac = True
            continue
        if in_ac:
            b = BULLET_RE.match(ln)
            if b and b.group(1).strip():
                ac.append(b.group(1).strip())
                continue
            if not ln.strip():
                continue
            if HEAD_RE.match(ln):
                in_ac = False
            elif ac and not BULLET_RE.match(ln) and ln.startswith((" ", "\t")):
                ac[-1] += " " + ln.strip()  # wrapped continuation line
                continue
            else:
                ac.append(ln.strip())  # plain line under the heading (e.g. PDF lost the bullet)
                continue
        if FIELD_RE.match(ln):
            continue
        desc.append(ln)

    if not summary:
        summary = next((l.strip(" #*") for l in desc if l.strip() and l.strip() != key), key)
        summary = KEY_RE.sub("", summary).strip(" :-") or key
        desc = [l for l in desc if l.strip(" #*") != summary and KEY_RE.sub("", l).strip(" :-#*") != summary]
    description_text = re.sub(r"\n{3,}", "\n\n", "\n".join(desc)).strip()
    return {"key": key, "summary": summary, "description_text": description_text, "acceptance_criteria": ac}


def to_issue_json(t):
    desc = t["description_text"]
    desc += ("\n\n" if desc else "") + "h3. Acceptance Criteria\n"
    desc += "\n".join(f"* {a}" for a in t["acceptance_criteria"]) if t["acceptance_criteria"] else "None given in the ticket file"
    return {"key": t["key"], "fields": {"summary": t["summary"], "description": desc, "labels": [t["key"]]}}


def _tickets_from_file(path):
    ext = os.path.splitext(path)[1].lower()
    stem_key = KEY_RE.search(os.path.basename(path).upper().replace("_", "-"))
    stem_key = stem_key.group(1) if stem_key else None
    if ext == ".json":
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
        issues = data.get("issues") if isinstance(data, dict) and "issues" in data else [data]
        return [i for i in issues if isinstance(i, dict) and i.get("key")], []
    if ext == ".csv":
        out = []
        with open(path, newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                key = (row.get("Labels") or row.get("Issue key") or "").strip()
                if KEY_RE.fullmatch(key):
                    out.append({"key": key, "fields": {"summary": row.get("Summary", ""),
                                "description": row.get("Description", ""), "labels": [key]}})
        return out, []
    t = parse_ticket_text(read_text(path), stem_key)
    if not t:
        return [], [f"{os.path.basename(path)}: no ticket key (e.g. RC3-5) found - skipped"]
    return [to_issue_json(t)], []


def import_inbox(inbox="tickets/inbox", out_dir="tickets/jira"):
    os.makedirs(out_dir, exist_ok=True)
    written, problems = [], []
    if not os.path.isdir(inbox):
        return written, [f"inbox folder not found: {inbox}"]
    for name in sorted(os.listdir(inbox)):
        path = os.path.join(inbox, name)
        if not os.path.isfile(path) or name.startswith("."):
            continue
        if os.path.splitext(name)[1].lower() not in (".txt", ".md", ".pdf", ".docx", ".json", ".csv"):
            problems.append(f"{name}: unsupported format - skipped")
            continue
        try:
            issues, probs = _tickets_from_file(path)
        except Exception as e:  # report, never crash the import
            problems.append(f"{name}: could not read ({type(e).__name__}: {e})")
            continue
        problems += probs
        for issue in issues:
            dest = os.path.join(out_dir, f"{issue['key']}.json")
            with open(dest, "w", encoding="utf-8") as f:
                json.dump(issue, f, indent=2, ensure_ascii=False)
            import story_fetcher
            n_ac = len(story_fetcher.parse_ac(issue["fields"].get("description") or ""))
            written.append(f"{name} -> {dest} ({n_ac} acceptance criteria)")
    return written, problems
