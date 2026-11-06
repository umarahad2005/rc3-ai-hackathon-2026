"""Fetch a ticket: live Jira (REST v2), a local folder of Jira issue JSON files, or the Task 1 CSV.

Order: JIRA_BASE_URL+JIRA_EMAIL+JIRA_API_TOKEN (live) > JIRA_TICKETS_DIR (local) > TICKETS_CSV.
A local file is exactly what GET /rest/api/2/issue/<KEY> returns, saved as <KEY>.json, or a Jira
search export {"issues": [...]}. Both go through the same parser as the live API.
"""
import csv
import glob
import json
import os
import re

import requests

import config


class TicketError(Exception):
    pass


NL = chr(10)
TICKET_RE =r"([A-Z][A-Z0-9]+-\d+)"


def extract_ticket_id(branch, title):
    for text in (branch, title):
        if not text:
            continue
        m = re.search(TICKET_RE, text)
        if m:
            return m.group(1)
    return None


def parse_ac(desc):
    m = re.search(r"h3\.\s*Acceptance Criteria\s*\n(.*?)(?=\nh3\.|\Z)", desc or "", re.S)
    if not m:
        return []
    return [ln.strip()[2:].strip() for ln in m.group(1).splitlines() if ln.strip().startswith("* ")]


def _ticket(tid, title, desc, source):
    desc = desc or ""
    return {"id": tid, "title": title or "", "description": desc,
            "acceptance_criteria": parse_ac(desc), "source": source}


def _from_jira(ticket_id, base, email, token):
    url = f"{base.rstrip('/')}/rest/api/2/issue/{ticket_id}"
    try:
        r = requests.get(url, params={"fields": "summary,description,labels"},
                         auth=(email, token), headers={"Accept": "application/json"}, timeout=15)
    except requests.RequestException as e:
        raise TicketError(f"Jira request failed for {ticket_id}: {type(e).__name__}") from e
    if r.status_code == 404:
        raise TicketError(f"Ticket {ticket_id} not found in Jira")
    if r.status_code >= 400:
        raise TicketError(f"Jira HTTP {r.status_code} for {ticket_id}")
    try:
        issue = r.json()
    except ValueError as e:
        raise TicketError(f"Jira returned invalid JSON for {ticket_id}") from e
    return _from_issue_json(ticket_id, issue, "jira")


def _adf_text(node):
    """Jira REST v3 returns the description as ADF JSON; rebuild wiki-style text for parse_ac."""
    if isinstance(node, str) or node is None:
        return node or ""
    t = node.get("type")
    kids = node.get("content") or []
    if t == "text":
        return node.get("text", "")
    if t == "heading":
        return f"h{node.get('attrs', {}).get('level', 3)}. " + "".join(_adf_text(k) for k in kids) + NL
    if t == "listItem":
        return "* " + "".join(_adf_text(k) for k in kids).strip() + NL
    if t == "paragraph":
        return "".join(_adf_text(k) for k in kids) + NL
    return "".join(_adf_text(k) for k in kids)


def _from_issue_json(ticket_id, issue, source):
    if not isinstance(issue, dict):
        raise TicketError(f"Ticket {ticket_id}: issue JSON is not an object")
    fields = issue.get("fields") or {}
    return _ticket(ticket_id, fields.get("summary"), _adf_text(fields.get("description")), source)


def _from_local_dir(ticket_id, folder):
    """Look for <KEY>.json, then any *.json search export holding an issue with that key."""
    if not os.path.isdir(folder):
        raise TicketError(f"JIRA_TICKETS_DIR is not a folder: {folder}")
    direct = os.path.join(folder, f"{ticket_id}.json")
    files = ([direct] if os.path.isfile(direct) else []) + sorted(glob.glob(os.path.join(folder, "*.json")))
    for path in files:
        try:
            with open(path, encoding="utf-8-sig") as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            raise TicketError(f"Cannot read local Jira file {os.path.basename(path)}: {type(e).__name__}") from e
        issues = data.get("issues") if isinstance(data, dict) and "issues" in data else [data]
        for issue in issues:
            if isinstance(issue, dict) and issue.get("key") == ticket_id:
                return _from_issue_json(ticket_id, issue, "jira-local")
    raise TicketError(f"Ticket {ticket_id} not found in JIRA_TICKETS_DIR")


def _from_csv(ticket_id, path):
    try:
        with open(path, newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                if (row.get("Labels") or "").strip() == ticket_id:
                    return _ticket(ticket_id, row.get("Summary"), row.get("Description"), "csv")
    except OSError as e:
        raise TicketError(f"Cannot read TICKETS_CSV: {e.strerror}") from e
    raise TicketError(f"Ticket {ticket_id} not found in CSV")


def fetch_ticket(ticket_id):
    base, email, token = config.get("JIRA_BASE_URL"), config.get("JIRA_EMAIL"), config.get("JIRA_API_TOKEN")
    if base and email and token:
        return _from_jira(ticket_id, base, email, token)
    folder = config.get("JIRA_TICKETS_DIR")
    if folder:
        return _from_local_dir(ticket_id, folder)
    path = config.get("TICKETS_CSV")
    if path:
        return _from_csv(ticket_id, path)
    raise TicketError("No ticket source configured (set JIRA_*, JIRA_TICKETS_DIR or TICKETS_CSV)")
