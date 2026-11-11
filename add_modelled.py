#!/usr/bin/env python3
"""
Add a new modelled export to the portal's "Modelled Dataset" tab (modelled/).

All modelled data lives in ONE tab, split by the quarter of each row's date.
A new month's export is not a new tab: it is appended here.

This script only ever ADDS. Rows already in modelled/ are kept as they are
(apart from the Dataset label, which is set to DATASET_LABEL on every row).

Steps:
  1. Job level for the new export (scraper_env2 venv, TensorFlow):
       cd "~/TwentySix/Data Scraping/Scraping 2.0"
       scraper_env2/bin/python apply_job_level.py --source <export.csv> --out ~/df_<mon>_job_level.csv
  2. Stage it OUTSIDE the repo with build_modelled.py:
       python3 build_modelled.py --source <export.csv> --job-levels ~/df_<mon>_job_level.csv \\
           --out-dir /tmp/staged_<mon> --prefix staged_
  3. Merge (dry run first). This also updates the Zigbert builder's adverts
     database (see builder_sync.py); --no-builder skips that:
       python3 add_modelled.py --staged /tmp/staged_<mon> --dry-run
       python3 add_modelled.py --staged /tmp/staged_<mon>

A staged row is dropped if it matches a row already published on
Date + Job Title + Company + Min Salary + Max Salary, the same key
add_new_quarters.py uses for the All UK Jobs tab. The same job seen again on a
later date is kept, as it always has been: each dated sighting is a row.
Remaining rows get Ids continuing from the highest published Id.

The touched quarter files are backed up to .modelled_backup/<timestamp>/ and
every quarter is re-sharded at 80 MB (GitHub Pages' limit is 100 MB).
"""

import argparse
import csv
import json
import shutil
import sys
import time
from pathlib import Path

from build_scraped4 import TARGET_COLS, SHARD_MAX_BYTES

REPO = Path(__file__).parent
OUT_DIR = REPO / "modelled"
BACKUP_DIR = REPO / ".modelled_backup"
FILE_PREFIX = "modelled_"
DATASET_LABEL = "Modelled Dataset"
KEY = ("Date", "Job Title", "Company", "Min Salary", "Max Salary")


def read_dir(d):
    """{quarter: [rows]} from a directory's quarters.json, in manifest order."""
    manifest = json.loads((d / "quarters.json").read_text(encoding="utf-8"))
    out = {}
    for q in manifest["quarters"]:
        rows = out.setdefault(q["id"], [])
        for name in q["files"]:
            with (d / name).open(newline="", encoding="utf-8") as f:
                rows.extend(csv.DictReader(f))
    return out


def write_quarter(q, rows):
    """Write one quarter, rolling to _a/_b/... shards past SHARD_MAX_BYTES."""
    names, fh, w = [], None, None

    def open_next():
        nonlocal fh, w
        if fh:
            fh.close()
        name = f"{FILE_PREFIX}{q}_{chr(ord('a') + len(names))}.csv"
        names.append(name)
        fh = (OUT_DIR / name).open("w", encoding="utf-8", newline="")
        w = csv.DictWriter(fh, fieldnames=TARGET_COLS)
        w.writeheader()

    open_next()
    for i, r in enumerate(rows):
        if i % 1000 == 0 and fh.tell() >= SHARD_MAX_BYTES:
            open_next()
        w.writerow(r)
    fh.close()
    if len(names) == 1:  # single file: no _a suffix
        (OUT_DIR / names[0]).rename(OUT_DIR / f"{FILE_PREFIX}{q}.csv")
        names = [f"{FILE_PREFIX}{q}.csv"]
    return names


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--staged", type=Path, required=True,
                    help="directory written by build_modelled.py --out-dir")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-builder", action="store_true",
                    help="do not update the Zigbert builder's adverts database afterwards")
    args = ap.parse_args(argv)
    csv.field_size_limit(sys.maxsize)

    if args.staged.resolve() == OUT_DIR.resolve():
        sys.exit("--staged must not be modelled/ itself")

    published = read_dir(OUT_DIR)
    staged = read_dir(args.staged)
    n_pub = sum(map(len, published.values()))
    n_new = sum(map(len, staged.values()))
    keys = {tuple(r[k] for k in KEY) for rows in published.values() for r in rows}
    next_id = max(int(r["Id"]) for rows in published.values() for r in rows) + 1
    print(f"Published: {n_pub:,} rows in {len(published)} quarters; next Id {next_id:,}")
    print(f"Staged:    {n_new:,} rows from {args.staged}")

    added, dropped = {}, 0
    for q, rows in staged.items():
        for r in rows:
            if tuple(r[k] for k in KEY) in keys:
                dropped += 1
                continue
            r["Id"] = next_id
            next_id += 1
            published.setdefault(q, []).append(r)
            added[q] = added.get(q, 0) + 1

    for rows in published.values():
        for r in rows:
            r["Dataset"] = DATASET_LABEL

    print(f"\nDropped {dropped:,} staged rows already published (same {' + '.join(KEY)})")
    print(f"Adding {sum(added.values()):,} rows:")
    for q in sorted(published, reverse=True):
        print(f"  {q}: +{added.get(q, 0):>7,}  -> {len(published[q]):>8,} rows")
    total = sum(map(len, published.values()))
    print(f"Total after merge: {total:,} rows")
    if args.dry_run:
        print("\nDRY RUN: nothing written.")
        return 0

    backup = BACKUP_DIR / time.strftime("%Y%m%d-%H%M%S")
    backup.mkdir(parents=True)
    for p in OUT_DIR.iterdir():
        shutil.copy2(p, backup / p.name)
    print(f"\nBacked up modelled/ to {backup}")
    for p in OUT_DIR.glob(FILE_PREFIX + "*.csv"):
        p.unlink()

    entries = []
    for q in sorted(published, reverse=True):
        files = write_quarter(q, published[q])
        entries.append({"id": q, "rows": len(published[q]), "files": files,
                        "bytes": sum((OUT_DIR / n).stat().st_size for n in files),
                        "dataset": DATASET_LABEL})
        print(f"  {q}: {len(published[q]):>8,} rows  {files}")
    (OUT_DIR / "quarters.json").write_text(
        json.dumps({"quarters": entries}, indent=2), encoding="utf-8")
    print(f"\nmodelled/quarters.json written: {len(entries)} quarters, {total:,} rows.")
    if not args.no_builder:
        from builder_sync import sync
        sync("modelled")
    return 0


if __name__ == "__main__":
    sys.exit(main())
