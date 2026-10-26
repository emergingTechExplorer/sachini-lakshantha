#!/usr/bin/env python3
"""Build the "Find your table" page from the guest list Google Sheet and event.json.

Usage:
    python3 build.py           download the guest list Sheet, then build
    python3 build.py --local   build from guests.csv without downloading

The Sheet's ID comes from the GUEST_SHEET_ID environment variable (set as a
secret on GitHub) or from the file .sheet-id next to this script. The Sheet must
be shared as "Anyone with the link can view". Each download also refreshes
guests.csv, so a local copy of the latest list is always on hand.

Writes:
    build/index.html    the page that gets published
    build/preview.html  the same page without the outer <html> wrapper, for Claude previews
"""
import base64
import csv
import io
import json
import os
import sys
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE / "template.html"
GUESTS = HERE / "guests.csv"
EVENT = HERE / "event.json"
FLORALS = {  # watercolour corners cropped from the wedding card
    "__FLORAL_TOP__": HERE / "floral-top.jpg",
    "__FLORAL_BOTTOM__": HERE / "floral-bottom.jpg",
}
SHEET_ID_FILE = HERE / ".sheet-id"  # not committed, so the Sheet link stays out of the public repo
OUT = HERE / "build"

BODY_MARKER = "<!-- body -->"
TABLE_MIN, TABLE_MAX = 8, 12  # warn outside this range; tables can be flexible

NOT_SHARED = ("Can't read the guest list Sheet. In Google Sheets, click Share and set "
              "General access to 'Anyone with the link' (Viewer).")


def sheet_id():
    sid = os.environ.get("GUEST_SHEET_ID", "").strip()
    if not sid and SHEET_ID_FILE.exists():
        sid = SHEET_ID_FILE.read_text(encoding="utf-8").strip()
    return sid


def download_sheet(sid):
    url = f"https://docs.google.com/spreadsheets/d/{sid}/export?format=csv"
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            text = r.read().decode("utf-8-sig")
            kind = r.headers.get("Content-Type", "")
    except urllib.error.HTTPError:
        sys.exit(NOT_SHARED)
    except urllib.error.URLError as e:
        sys.exit(f"Couldn't download the guest list Sheet: {e.reason}")
    # A Sheet that isn't shared answers with Google's sign-in page instead of CSV.
    if "text/csv" not in kind:
        sys.exit(NOT_SHARED)
    return text


def load_guests(text):
    guests, problems = [], []
    rows = csv.DictReader(io.StringIO(text))
    # Match headers loosely, so "Name", "Table" and "Household (optional)" all work.
    columns = {(h or "").strip().lower().split(" ")[0]: h for h in rows.fieldnames or []}
    if "name" not in columns or "table" not in columns:
        sys.exit("The guest list needs a 'Name' column and a 'Table' column in its first row.")
    for line, row in enumerate(rows, start=2):
        get = lambda key: (row.get(columns.get(key, ""), "") or "").strip()
        name, table = get("name"), get("table")
        if not name:
            continue
        if not table:
            problems.append(f"row {line}: {name} has no table")
            continue
        guests.append({"name": name, "table": table, "household": get("household")})
    return guests, problems


def to_js(value):
    # Escape "</" so a name can never close the <script> tag early.
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


def main():
    event = json.loads(EVENT.read_text(encoding="utf-8"))

    sid = "" if "--local" in sys.argv else sheet_id()
    if sid:
        text = download_sheet(sid)
        GUESTS.write_text(text, encoding="utf-8")
        source = "the Google Sheet"
    else:
        text = GUESTS.read_text(encoding="utf-8-sig")
        source = "guests.csv"
    guests, problems = load_guests(text)

    if not guests:
        sys.exit(f"No guests found in {source}, so the page was not rebuilt.")

    table_ids = {str(t["id"]) for t in event["tables"]}
    for g in guests:
        if g["table"] not in table_ids:
            problems.append(f"{g['name']} is at table {g['table']}, which is not in event.json")

    if problems:
        print(f"Fix these in {source}, then run again:")
        for p in problems:
            print("  -", p)
        sys.exit(1)

    dupes = [n for n, c in Counter(g["name"].lower() for g in guests).items() if c > 1]
    counts = Counter(g["table"] for g in guests)

    page = (TEMPLATE.read_text(encoding="utf-8")
            .replace("/*GUESTS*/[]", to_js(guests))
            .replace("/*EVENT*/{}", to_js(event)))
    for marker, image in FLORALS.items():
        uri = ""
        if image.exists():
            uri = "data:image/jpeg;base64," + base64.b64encode(image.read_bytes()).decode()
        page = page.replace(marker, uri)

    head, body = page.split(BODY_MARKER)
    OUT.mkdir(exist_ok=True)
    (OUT / "preview.html").write_text(head + body, encoding="utf-8")
    (OUT / "index.html").write_text(
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
        f"{head}</head>\n<body>\n{body}</body>\n</html>\n",
        encoding="utf-8",
    )

    print(f"Built {len(guests)} guests from {source} across {len(counts)} tables -> build/index.html")
    for t in event["tables"]:
        n = counts.get(str(t["id"]), 0)
        flag = "" if TABLE_MIN <= n <= TABLE_MAX else "   <- check size"
        print(f"  Table {t['id']:>2} {t.get('name', ''):<12} {n:>2} guests{flag}")
    for n in dupes:
        print(f"  Note: more than one guest named '{n}'. The page shows both with their tables.")


if __name__ == "__main__":
    main()
