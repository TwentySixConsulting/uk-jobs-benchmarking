#!/usr/bin/env python3
"""
DO NOT RUN THIS. Use add_new_quarters.py instead.

This script rebuilds every quarter file from the source CSV. That is no longer
safe. The source was regenerated on 2026-07-01 and is now SMALLER than what is
published in quarters/ (1,251,109 rows against 1,609,638), so running this would
overwrite the published data with the smaller set and permanently lose roughly
360,000 rows that exist nowhere else.

Kept for reference only. See README.md, "Updating the data".

--- original docstring follows ---

Split the 2026 processed_scraped_data CSV (~2.6 GB) into per-quarter CSVs
matching the 13-column schema used by the housing-association-benchmarking site.

Run from the repo root:
    python3 build_quarters.py

Outputs:
    quarters/<YYYYQN>.csv  (one per quarter present in source)
    quarters/quarters.json (newest-first index for the web UI)
"""


import csv
import json
import os
import sys
from pathlib import Path

SOURCE = Path(
    "/Users/millieharrison/TwentySix/Data Scraping/Scraping 2.0/"
    "Processed Data 2026/processed_scraped_data2026.csv"
)
OUT_DIR = Path(__file__).parent / "quarters"

# Truncate description to keep file sizes down (table view itself truncates to 300 chars)
DESC_MAX = 250
# GitHub Pages won't serve files >100 MB; keep each shard comfortably under that
SHARD_MAX_BYTES = 80 * 1024 * 1024

COLUMN_MAP = [
    # "Id" is generated sequentially below — the source `id` column is mostly empty.
    ("Date",           "date"),
    ("Job Title",      "job_title"),
    ("Company",        "company"),
    ("Location",       "location"),
    ("Region",         "region"),
    ("Function",       "function"),
    ("Job Level",      "job_level"),
    ("Industry",       "industry"),
    ("Salary Period",  "salary_period"),
    ("Min Salary",     "min_salary"),
    ("Max Salary",     "max_salary"),
    ("Job Description","description"),
]
TARGET_COLS = ["Id"] + [c for c, _ in COLUMN_MAP]


def main() -> int:
    if not SOURCE.exists():
        print(f"ERROR: source CSV not found at {SOURCE}", file=sys.stderr)
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    csv.field_size_limit(sys.maxsize)

    # For each quarter we keep a rolling shard. Once the current shard file
    # exceeds SHARD_MAX_BYTES on disk, we close it and start the next one.
    # state[q] = {"shard": int, "writer": DictWriter, "fh": file, "rows": int, "files": [filenames]}
    state = {}
    seen = {}       # quarter -> set of job_id already written
    counts = {}     # quarter -> total rows written across shards
    next_id = 1     # global sequential Id assigned in source order
    total = 0
    skipped_no_quarter = 0
    skipped_dupes = 0

    def open_shard(q: str, idx: int):
        # Single shard → "2025Q1.csv". Multi-shard → "2025Q1_a.csv", "2025Q1_b.csv", ...
        suffix = "" if idx == 0 else f"_{chr(ord('a') + idx)}"
        name = f"{q}{suffix}.csv"
        fh = (OUT_DIR / name).open("w", encoding="utf-8", newline="")
        dw = csv.DictWriter(fh, fieldnames=TARGET_COLS)
        dw.writeheader()
        return name, dw, fh

    def rename_first_shard_if_needed(q: str):
        """When a quarter ends with multiple shards, the first one was written as
        'Q.csv' but should be 'Q_a.csv' for consistency. Fix that retroactively."""
        st = state[q]
        if len(st["files"]) > 1 and st["files"][0] == f"{q}.csv":
            old = OUT_DIR / f"{q}.csv"
            new_name = f"{q}_a.csv"
            old.rename(OUT_DIR / new_name)
            st["files"][0] = new_name

    print(f"Reading {SOURCE}")
    with SOURCE.open("r", encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            total += 1
            if total % 250_000 == 0:
                print(f"  ...{total:,} rows scanned, {sum(counts.values()):,} written")

            q = (row.get("year_quarter") or "").strip()
            if not q:
                skipped_no_quarter += 1
                continue

            jid = row.get("job_id") or ""
            quarter_seen = seen.setdefault(q, set())
            if jid and jid in quarter_seen:
                skipped_dupes += 1
                continue
            if jid:
                quarter_seen.add(jid)

            out_row = {}
            for tgt, src in COLUMN_MAP:
                v = row.get(src, "")
                if v is None:
                    v = ""
                out_row[tgt] = v
            desc = out_row["Job Description"] or ""
            if len(desc) > DESC_MAX:
                desc = desc[:DESC_MAX]
            out_row["Job Description"] = desc
            out_row["Id"] = next_id
            next_id += 1

            st = state.get(q)
            if st is None:
                name, dw, fh = open_shard(q, 0)
                st = {"shard": 0, "writer": dw, "fh": fh, "files": [name]}
                state[q] = st
                counts[q] = 0
            st["writer"].writerow(out_row)
            counts[q] += 1

            # Roll to next shard if current file is approaching the limit.
            # tell() reports the buffered position; flush periodically to keep it accurate.
            if counts[q] % 5_000 == 0:
                st["fh"].flush()
                if st["fh"].tell() >= SHARD_MAX_BYTES:
                    st["fh"].close()
                    st["shard"] += 1
                    name, dw, fh = open_shard(q, st["shard"])
                    st["writer"] = dw
                    st["fh"] = fh
                    st["files"].append(name)

    for q, st in state.items():
        st["fh"].close()
        rename_first_shard_if_needed(q)

    # Write quarters.json — newest first
    def quarter_sort_key(qid: str):
        try:
            y, qn = qid.split("Q")
            return (int(y), int(qn))
        except Exception:
            return (0, 0)

    ordered = sorted(counts.keys(), key=quarter_sort_key, reverse=True)
    index = {
        "quarters": [
            {
                "id": q,
                "rows": counts[q],
                "files": state[q]["files"],
                "bytes": sum((OUT_DIR / fn).stat().st_size for fn in state[q]["files"]),
            }
            for q in ordered
        ]
    }
    (OUT_DIR / "quarters.json").write_text(json.dumps(index, indent=2), encoding="utf-8")

    print()
    print(f"Source rows scanned:      {total:,}")
    print(f"Rows written:             {sum(counts.values()):,}")
    print(f"Skipped (no year_quarter):{skipped_no_quarter:,}")
    print(f"Skipped (duplicate id):   {skipped_dupes:,}")
    print()
    print("Per-quarter output:")
    for q in ordered:
        total_bytes = sum((OUT_DIR / fn).stat().st_size for fn in state[q]["files"])
        size_mb = total_bytes / 1024 / 1024
        shard_note = f" across {len(state[q]['files'])} shard(s)" if len(state[q]["files"]) > 1 else ""
        print(f"  {q}: {counts[q]:>8,} rows, {size_mb:6.1f} MB{shard_note}")
    print()
    print(f"Wrote {OUT_DIR / 'quarters.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
