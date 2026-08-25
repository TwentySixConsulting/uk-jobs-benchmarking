#!/usr/bin/env python3
"""
Additive top-up for the portal's quarter files.

build_quarters.py rebuilds every quarter from the source CSV. That is no longer
safe: the source CSV was regenerated on 2026-07-01 and came out SMALLER than the
data already published here (1,251,109 rows vs the portal's 1,609,638), so a full
rebuild would silently drop rows the portal is the only remaining copy of.

This script only ever ADDS. It never rewrites an existing row.

For each quarter named in QUARTERS:
  - reads the source rows for that quarter
  - drops duplicates by job_id, the same way build_quarters.py does
  - drops any row already published, matched on Date + Job Title + Company +
    Min Salary + Max Salary (the published files carry no job_id, so this
    content key is the best available match)
  - appends what is left, continuing the global sequential Id
  - creates the quarter file if the portal does not have that quarter yet

Then it updates quarters.json (row counts, byte sizes, newest-first order).

Run from the repo root:
    python3 add_new_quarters.py --dry-run
    python3 add_new_quarters.py
"""

import argparse
import csv
import glob
import json
import os
import shutil
import sys
from pathlib import Path

SOURCE = Path(
    "/Users/millieharrison/TwentySix/Data Scraping/Scraping 2.0/"
    "Processed Data 2026/processed_scraped_data2026.csv"
)
OUT_DIR = Path(__file__).parent / "quarters"
BACKUP_DIR = Path(__file__).parent / ".quarters_backup"

QUARTERS = ["2026Q2", "2026Q3"]

DESC_MAX = 250
SHARD_MAX_BYTES = 80 * 1024 * 1024

COLUMN_MAP = [
    ("Date",            "date"),
    ("Job Title",       "job_title"),
    ("Company",         "company"),
    ("Location",        "location"),
    ("Region",          "region"),
    ("Function",        "function"),
    ("Job Level",       "job_level"),
    ("Industry",        "industry"),
    ("Salary Period",   "salary_period"),
    ("Min Salary",      "min_salary"),
    ("Max Salary",      "max_salary"),
    ("Job Description", "description"),
]
TARGET_COLS = ["Id"] + [c for c, _ in COLUMN_MAP]

MATCH_FIELDS = ["Date", "Job Title", "Company", "Min Salary", "Max Salary"]


def content_key(row):
    return tuple((row.get(f) or "").strip() for f in MATCH_FIELDS)


def quarter_sort_key(qid):
    try:
        y, qn = qid.split("Q")
        return (int(y), int(qn))
    except Exception:
        return (0, 0)


def published_files_for(q):
    """Existing files for a quarter, in shard order."""
    single = OUT_DIR / f"{q}.csv"
    if single.exists():
        return [single.name]
    shards = sorted(p.name for p in OUT_DIR.glob(f"{q}_[a-z].csv"))
    return shards


def scan_published():
    """Return (max_id, total_rows, {quarter: set(content_key)}, {quarter: rows})."""
    csv.field_size_limit(sys.maxsize)
    max_id = 0
    total = 0
    keys = {q: set() for q in QUARTERS}
    per_quarter = {}

    for path in sorted(OUT_DIR.glob("*.csv")):
        q = path.stem.split("_")[0]
        n = 0
        with path.open(newline="", encoding="utf-8", errors="replace") as f:
            for row in csv.DictReader(f):
                n += 1
                total += 1
                try:
                    max_id = max(max_id, int(row["Id"]))
                except (TypeError, ValueError):
                    pass
                if q in keys:
                    keys[q].add(content_key(row))
        per_quarter[q] = per_quarter.get(q, 0) + n
    return max_id, total, keys, per_quarter


def read_source_rows():
    """Pull the source rows for the quarters we care about, in file order."""
    csv.field_size_limit(sys.maxsize)
    wanted = set(QUARTERS)
    out = {q: [] for q in QUARTERS}
    seen_job_ids = {q: set() for q in QUARTERS}
    dupes = {q: 0 for q in QUARTERS}
    scanned = 0

    with SOURCE.open("r", encoding="utf-8", errors="replace", newline="") as f:
        for row in csv.DictReader(f):
            scanned += 1
            if scanned % 250_000 == 0:
                print(f"  ...{scanned:,} source rows scanned", flush=True)
            q = (row.get("year_quarter") or "").strip()
            if q not in wanted:
                continue
            jid = row.get("job_id") or ""
            if jid:
                if jid in seen_job_ids[q]:
                    dupes[q] += 1
                    continue
                seen_job_ids[q].add(jid)
            rec = {}
            for tgt, src in COLUMN_MAP:
                rec[tgt] = row.get(src) or ""
            desc = rec["Job Description"]
            if len(desc) > DESC_MAX:
                desc = desc[:DESC_MAX]
            rec["Job Description"] = desc
            out[q].append(rec)
    print(f"  {scanned:,} source rows scanned total")
    return out, dupes


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would be added without writing anything")
    args = ap.parse_args(argv)

    if not SOURCE.exists():
        print(f"ERROR: source CSV not found at {SOURCE}", file=sys.stderr)
        return 1

    print("Scanning published quarter files...")
    max_id, published_total, published_keys, per_quarter = scan_published()
    print(f"  published rows: {published_total:,}, highest Id: {max_id:,}")
    for q in QUARTERS:
        print(f"  {q} currently published: {per_quarter.get(q, 0):,} rows")

    print(f"\nReading source for {', '.join(QUARTERS)}...")
    source_rows, dupes = read_source_rows()

    to_add = {}
    for q in QUARTERS:
        rows = source_rows[q]
        fresh = [r for r in rows if content_key(r) not in published_keys[q]]
        to_add[q] = fresh
        print(f"\n{q}:")
        print(f"  source rows (after job_id dedup): {len(rows):,}  "
              f"(dropped {dupes[q]:,} duplicate job_id)")
        print(f"  already published:                {len(rows) - len(fresh):,}")
        print(f"  to add:                           {len(fresh):,}")

    total_new = sum(len(v) for v in to_add.values())
    print(f"\nTotal rows to add: {total_new:,}")
    print(f"Portal would go from {published_total:,} to {published_total + total_new:,} rows")

    if total_new == 0:
        print("Nothing to add.")
        return 0

    if args.dry_run:
        print("\nDRY RUN: no files written.")
        return 0

    # Back up everything we are about to touch, plus the index.
    BACKUP_DIR.mkdir(exist_ok=True)
    for q in QUARTERS:
        for fn in published_files_for(q):
            shutil.copy2(OUT_DIR / fn, BACKUP_DIR / fn)
    shutil.copy2(OUT_DIR / "quarters.json", BACKUP_DIR / "quarters.json")
    print(f"\nBacked up touched files to {BACKUP_DIR}")

    next_id = max_id + 1
    for q in QUARTERS:
        rows = to_add[q]
        if not rows:
            continue
        existing = published_files_for(q)
        if existing:
            target = OUT_DIR / existing[-1]      # append to the last shard
            mode = "a"
            write_header = False
        else:
            target = OUT_DIR / f"{q}.csv"
            mode = "w"
            write_header = True

        with target.open(mode, encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=TARGET_COLS)
            if write_header:
                w.writeheader()
            for r in rows:
                r["Id"] = next_id
                next_id += 1
                w.writerow(r)
        size_mb = target.stat().st_size / 1024 / 1024
        print(f"  {q}: wrote {len(rows):,} rows to {target.name} "
              f"({size_mb:.1f} MB)")
        if target.stat().st_size >= SHARD_MAX_BYTES:
            print(f"    NOTE: {target.name} is over the {SHARD_MAX_BYTES/1024/1024:.0f} MB "
                  f"shard threshold and should be split before the next top-up.")

    # Rebuild quarters.json from what is actually on disk.
    counts = {}
    files_by_q = {}
    csv.field_size_limit(sys.maxsize)
    for path in sorted(OUT_DIR.glob("*.csv")):
        q = path.stem.split("_")[0]
        with path.open(newline="", encoding="utf-8", errors="replace") as f:
            n = sum(1 for _ in csv.DictReader(f))
        counts[q] = counts.get(q, 0) + n
        files_by_q.setdefault(q, []).append(path.name)

    ordered = sorted(counts, key=quarter_sort_key, reverse=True)
    index = {
        "quarters": [
            {
                "id": q,
                "rows": counts[q],
                "files": sorted(files_by_q[q]),
                "bytes": sum((OUT_DIR / fn).stat().st_size for fn in files_by_q[q]),
            }
            for q in ordered
        ]
    }
    (OUT_DIR / "quarters.json").write_text(json.dumps(index, indent=2), encoding="utf-8")

    grand = sum(counts.values())
    print(f"\nquarters.json rewritten. Portal now has {grand:,} rows "
          f"across {len(ordered)} quarters.")
    print(f"Newest quarter (the UI default) is now {ordered[0]}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
