"""Turn the Task 1 tickets_jira.csv into local Jira issue files, in the same shape as
GET /rest/api/2/issue/<KEY>, so the reviewer can run offline with JIRA_TICKETS_DIR.

Usage: python csv_to_jira_json.py tickets/clear_tickets_jira.csv tickets/jira
"""
import csv
import json
import os
import sys


def convert(csv_path, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    written = []
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            key = (row.get("Labels") or "").strip()
            if not key:
                continue
            issue = {"key": key, "fields": {
                "summary": row.get("Summary", ""),
                "issuetype": {"name": row.get("Issue Type", "")},
                "description": row.get("Description", ""),
                "priority": {"name": row["Priority"]} if row.get("Priority") else None,
                "labels": [key]}}
            path = os.path.join(out_dir, f"{key}.json")
            with open(path, "w", encoding="utf-8") as out:
                json.dump(issue, out, indent=2, ensure_ascii=False)
            written.append(path)
    return written


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    for p in convert(sys.argv[1], sys.argv[2]):
        print("wrote", p)
