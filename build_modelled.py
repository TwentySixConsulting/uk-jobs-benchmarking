#!/usr/bin/env python3
"""
Build the "October 2026, Modelled Dataset" files for the portal's first tab.

Reads the refined export (df_325k_final_run_10_26.csv, ~2.3 GB, 155 columns)
and writes portal-shaped CSVs plus a manifest into modelled/. Nothing in
quarters/ is read or written, so the "All UK Jobs" tab is never affected.

Same 14-column schema as quarters/, so index.html treats both tabs alike.
Blank classification fields are written as "Not classified", because the
portal's applyFilters silently drops rows whose checklist value is blank.
Job Level is entirely empty in this file and is hidden on this tab.

Run from the repo root:
    python3 build_modelled.py --dry-run     # counts only, writes nothing
    python3 build_modelled.py
"""

import argparse
import csv
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from build_scraped4 import (TARGET_COLS, FILL_BLANK, NOT_CLASSIFIED, DESC_MAX,
                            SHARD_MAX_BYTES, REL_AGO, parse_scraped,
                            resolve_date, quarter_of, _sal)

REPO = Path(__file__).parent
OUT_DIR = REPO / "modelled"
DEFAULT_SOURCE = Path("/Users/millieharrison/df_325k_final_run_10_26.csv")

DATASET_LABEL = "October 2026, Modelled Dataset"
FILE_PREFIX = "modelled_"

WS = re.compile(r"\s+")
FRAC = re.compile(r"\.(\d+)")


def parse_ts(s):
    """parse_scraped, but tolerant of 1-5 digit fractional seconds, which
    older Pythons' fromisoformat rejects; falls back to the date part."""
    if not s:
        return None
    s = FRAC.sub(lambda m: "." + m.group(1)[:6].ljust(6, "0"), s.strip(), count=1)
    return parse_scraped(s) or parse_scraped(s[:10])


def normalise_date_text(raw):
    """'Posted 1 week ago', '3 hrs ago', '1 day ago Apply' -> forms REL_AGO knows."""
    low = raw.lower()
    if low.startswith("posted "):
        raw = raw[7:]
    raw = re.sub(r"\b(hr|hrs)\b", "hour", raw, flags=re.I)
    raw = re.sub(r"\b(min|mins)\b", "minute", raw, flags=re.I)
    m = re.match(r"\s*(\d+\s+\w+?s?\s+ago)\b", raw, re.I)
    return m.group(1) if m else raw


def description(r):
    for col in ("description", "description_no_noise", "full_description"):
        v = WS.sub(" ", r.get(col) or "").strip()
        if v and v.lower() not in ("expired", "nan"):
            return v[:DESC_MAX]
    return ""


def salary(v):
    v = _sal(v)
    if v == "":
        return ""
    f = float(v)
    return int(f) if f.is_integer() else round(f, 2)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    csv.field_size_limit(sys.maxsize)
    if not args.dry_run:
        OUT_DIR.mkdir(exist_ok=True)
        for p in OUT_DIR.glob(FILE_PREFIX + "*.csv"):
            p.unlink()

    writers, handles, counts, files_by_q = {}, {}, {}, {}
    filled = {f: 0 for f in FILL_BLANK}
    date_source = {"iso": 0, "relative": 0, "fallback": 0, "none": 0}
    seen_ids = set()
    dupes = no_salary = total = 0
    next_id = 1
    t0 = time.time()

    def shard_for(q):
        """Open (or roll to) the current shard file for a quarter."""
        if q in handles:
            h = handles[q]
            h.flush()
            if h.tell() < SHARD_MAX_BYTES:
                return writers[q]
            h.close()
            idx = len(files_by_q[q])
            if idx == 1:
                # First roll-over: rename the unsuffixed file to _a
                first = files_by_q[q][0]
                renamed = f"{FILE_PREFIX}{q}_a.csv"
                (OUT_DIR / first).rename(OUT_DIR / renamed)
                files_by_q[q][0] = renamed
            name = f"{FILE_PREFIX}{q}_{chr(ord('a') + idx)}.csv"
        else:
            name = f"{FILE_PREFIX}{q}.csv"
            files_by_q[q] = []
        fh = (OUT_DIR / name).open("w", encoding="utf-8", newline="")
        dw = csv.DictWriter(fh, fieldnames=TARGET_COLS)
        dw.writeheader()
        handles[q], writers[q] = fh, dw
        files_by_q[q].append(name)
        return dw

    with args.source.open(newline="", encoding="utf-8", errors="replace") as f:
        for r in csv.DictReader(f):
            total += 1
            src_id = r.get("id")
            if src_id:
                if src_id in seen_ids:
                    dupes += 1
                    continue
                seen_ids.add(src_id)

            ref_dt = parse_ts(r.get("scraped")) or parse_ts(r.get("created_at"))
            raw_date = normalise_date_text((r.get("date") or "").strip())
            date = resolve_date(raw_date, ref_dt)
            if raw_date[4:5] == "-" and len(raw_date) >= 10:
                date_source["iso"] += 1
            elif REL_AGO.match(raw_date):
                date_source["relative"] += 1
            elif date:
                date_source["fallback"] += 1
            else:
                date_source["none"] += 1
            try:
                q = quarter_of(datetime.fromisoformat(date))
            except ValueError:
                q = None
            if not q:
                continue

            out = {
                "Id": next_id,
                "Date": date,
                "Job Title": WS.sub(" ", r.get("job_title") or "").strip(),
                "Company": (r.get("company") or "").strip(),
                "Location": WS.sub(" ", r.get("location") or "").strip(),
                "Region": (r.get("region") or "").strip(),
                "Function": (r.get("function") or "").strip(),
                "Job Level": (r.get("job_level") or "").strip(),
                "Industry": (r.get("industry") or "").strip(),
                "Salary Period": (r.get("salary_period") or "").strip(),
                "Min Salary": salary(r.get("min_salary")),
                "Max Salary": salary(r.get("max_salary")),
                "Job Description": description(r),
                "Dataset": DATASET_LABEL,
            }
            if out["Min Salary"] == "" and out["Max Salary"] == "":
                no_salary += 1
            for fld in FILL_BLANK:
                if not str(out[fld]).strip():
                    out[fld] = NOT_CLASSIFIED
                    filled[fld] += 1

            next_id += 1
            counts[q] = counts.get(q, 0) + 1
            if not args.dry_run:
                shard_for(q).writerow(out)
            if total % 50_000 == 0:
                print(f"  {total:,} rows read, {time.time() - t0:.0f}s", flush=True)

    for h in handles.values():
        h.close()

    written = sum(counts.values())
    print(f"\nRead {total:,} rows in {time.time() - t0:.0f}s; "
          f"{dupes:,} duplicate ids dropped; {written:,} written")
    print("\nRows per quarter:")
    for q in sorted(counts):
        names = files_by_q.get(q, [])
        size = sum((OUT_DIR / n).stat().st_size for n in names) if names else 0
        print(f"  {q}: {counts[q]:>8,} rows  {size/1024/1024:6.1f} MB  {names}")
    print("\nDate resolution:")
    for k, v in date_source.items():
        print(f"  {k:9s} {v:7,}  {100*v/max(total,1):5.1f}%")
    print(f"\nRows with no usable salary (written blank): {no_salary:,}")
    print(f'\nBlanks filled with "{NOT_CLASSIFIED}":')
    for fld, n in filled.items():
        print(f"  {fld:15s} {n:7,}  {100*n/max(written,1):5.1f}%")

    if args.dry_run:
        print("\nDRY RUN: no files written.")
        return 0

    entries = [{
        "id": q,
        "rows": counts[q],
        "files": files_by_q[q],
        "bytes": sum((OUT_DIR / n).stat().st_size for n in files_by_q[q]),
        "dataset": DATASET_LABEL,
    } for q in sorted(counts, reverse=True)]
    (OUT_DIR / "quarters.json").write_text(
        json.dumps({"quarters": entries}, indent=2), encoding="utf-8")
    print(f"\nmodelled/quarters.json written: {len(entries)} quarters, {written:,} rows.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
