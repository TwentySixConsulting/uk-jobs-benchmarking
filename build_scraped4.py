#!/usr/bin/env python3
"""
Pull the twentysix_scraped4 Supabase table into portal quarter files.

This is a SECOND dataset alongside the main scrape. It is written to its own
files (scraped4_<quarter>.csv) and tagged with a "Dataset" column so the UI can
label and filter it. No main-scrape file is ever touched.

The scraped4 model is missing most of the classification codes (job_level is
entirely empty, function 1.4%, industry 3.2%), so blanks are written as
"Not classified" rather than left empty. That is not cosmetic: the portal's
applyFilters does filters[field].has(row[field]) against a value set built from
non-blank values only, so a genuinely blank cell makes the whole row invisible.

Run from the repo root:
    python3 build_scraped4.py --dry-run     # counts only, writes nothing
    python3 build_scraped4.py

A refresh never loses published rows: any Scraped4 row already in the portal that
Supabase no longer has (same title, employer and pay) is kept. Afterwards the
builder's adverts database is updated too (builder_sync.py; --no-builder skips).
"""

import argparse
import csv
import gzip
import io
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).parent
OUT_DIR = REPO / "quarters"
ENV_FILE = Path("/Users/millieharrison/twentysix-salary-portal-v2/.env.local")

TABLE = "twentysix_scraped4"
DATASET_LABEL = "Scraped4"
MAIN_LABEL = "Main scrape"
NOT_CLASSIFIED = "Not classified"

DESC_MAX = 250
PAGE = 500
SHARD_MAX_BYTES = 80 * 1024 * 1024

TARGET_COLS = ["Id", "Date", "Job Title", "Company", "Location", "Region",
               "Function", "Job Level", "Industry", "Salary Period",
               "Min Salary", "Max Salary", "Job Description", "Dataset"]

# Fields we fill with NOT_CLASSIFIED when empty, so rows stay visible/filterable.
FILL_BLANK = ["Region", "Function", "Job Level", "Industry", "Salary Period"]

SELECT = ("id,date,job_title,company,location,region,function,job_level,industry,"
          "salary_period,min_salary,max_salary,description,full_description,scraped")

MONTHS = {m.lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], 1)}
for _m, _i in list(MONTHS.items()):
    MONTHS[_m[:3]] = _i


def load_env():
    env = {}
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k] = v.strip().strip('"').strip("'")
    return env["NEXT_PUBLIC_SUPABASE_URL"], env["NEXT_PUBLIC_SUPABASE_ANON_KEY"]


def parse_scraped(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


REL_AGO = re.compile(r"^\s*(\d+)\s+(minute|hour|day|week|month)s?\s+ago\s*$", re.I)
DAY_MONTH = re.compile(r"^\s*(\d{1,2})\s+([A-Za-z]{3,9})\s*$")


def resolve_date(raw, scraped_dt):
    """
    The scraped4 `date` column is 63% relative text, 24% ISO, 13% null.
    Return YYYY-MM-DD, falling back to the scrape date.

    "N days left" is a CLOSING date, not a posting date, so it is not used.
    """
    fallback = scraped_dt.date().isoformat() if scraped_dt else ""
    if not raw:
        return fallback
    raw = str(raw).strip()

    # ISO timestamp or date
    if len(raw) >= 10 and raw[4:5] == "-" and raw[7:8] == "-":
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).date().isoformat()
        except ValueError:
            return raw[:10]

    low = raw.lower()
    if low in ("today", "just now"):
        return fallback
    if low == "yesterday":
        return (scraped_dt - timedelta(days=1)).date().isoformat() if scraped_dt else fallback

    m = REL_AGO.match(raw)
    if m and scraped_dt:
        n, unit = int(m.group(1)), m.group(2).lower()
        delta = {"minute": timedelta(minutes=n), "hour": timedelta(hours=n),
                 "day": timedelta(days=n), "week": timedelta(weeks=n),
                 "month": timedelta(days=30 * n)}[unit]
        return (scraped_dt - delta).date().isoformat()

    m = DAY_MONTH.match(raw)
    if m and scraped_dt:
        day, mon = int(m.group(1)), MONTHS.get(m.group(2).lower())
        if mon:
            year = scraped_dt.year
            try:
                d = datetime(year, mon, day, tzinfo=timezone.utc)
            except ValueError:
                return fallback
            # A date later than the scrape almost certainly belongs to last year
            if d.date() > scraped_dt.date():
                try:
                    d = datetime(year - 1, mon, day, tzinfo=timezone.utc)
                except ValueError:
                    return fallback
            return d.date().isoformat()

    # "N days left", "Closes ...", anything else -> use the scrape date
    return fallback


def _sal(v):
    """Salary or blank. 0 means 'not known here', not 'this job pays nothing'."""
    try:
        return v if v is not None and float(v) > 0 else ""
    except (TypeError, ValueError):
        return ""


def quarter_of(dt):
    return f"{dt.year}Q{(dt.month - 1) // 3 + 1}" if dt else None


def fetch_page(url, key, after):
    params = {"select": SELECT, "order": "id.asc", "limit": PAGE}
    if after is not None:
        params["id"] = f"gt.{after}"
    q = urllib.parse.urlencode(params)
    req = urllib.request.Request(
        f"{url}/rest/v1/{TABLE}?{q}",
        headers={"apikey": key, "Authorization": f"Bearer {key}",
                 "Accept-Encoding": "gzip"})
    last = None
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                raw = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                return json.loads(raw.decode("utf-8"))
        except Exception as e:                      # noqa: BLE001
            last = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"page after id={after} failed after 5 tries: {last}")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-builder", action="store_true",
                    help="do not update the Zigbert builder's adverts database afterwards")
    ap.add_argument("--limit", type=int, default=0,
                    help="stop after N rows (for testing)")
    args = ap.parse_args(argv)

    url, key = load_env()
    csv.field_size_limit(sys.maxsize)

    # Continue the portal's global sequential Id.
    max_id = 0
    for p in OUT_DIR.glob("*.csv"):
        if p.name.startswith("scraped4_"):
            continue
        with p.open(newline="", encoding="utf-8", errors="replace") as f:
            for row in csv.DictReader(f):
                try:
                    max_id = max(max_id, int(row["Id"]))
                except (TypeError, ValueError, KeyError):
                    pass
    print(f"Highest Id already published: {max_id:,}")
    next_id = max_id + 1

    # Scraped4 rows published before this refresh. Supabase updates or deletes
    # rows over time; a published row that is no longer there is kept (appended
    # back after the fetch), so a refresh never loses adverts. Read now, because
    # the fetch below overwrites these files.
    previous = []
    if not args.dry_run:
        try:
            old_index = json.loads((OUT_DIR / "quarters.json").read_text())
        except (OSError, ValueError):
            old_index = {"quarters": []}
        for e in old_index.get("quarters", []):
            if e.get("dataset") != DATASET_LABEL:
                continue
            q = e.get("quarter") or e["id"].split(":")[-1]
            for name in e.get("files", []):
                path = OUT_DIR / name
                if path.exists():
                    with path.open(newline="", encoding="utf-8", errors="replace") as f:
                        previous.extend((q, r) for r in csv.DictReader(f))
        print(f"{len(previous):,} Scraped4 rows published before this refresh")

    writers, handles, counts, files_by_q = {}, {}, {}, {}
    filled = {f: 0 for f in FILL_BLANK}
    date_source = {"iso": 0, "relative": 0, "fallback": 0}
    zero_salary = 0
    total = 0
    after = None
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
            name = f"scraped4_{q}_{chr(ord('a') + idx)}.csv"
        else:
            name = f"scraped4_{q}.csv"
            files_by_q[q] = []
        fh = (OUT_DIR / name).open("w", encoding="utf-8", newline="")
        dw = csv.DictWriter(fh, fieldnames=TARGET_COLS)
        dw.writeheader()
        handles[q], writers[q] = fh, dw
        files_by_q[q].append(name)
        return dw

    while True:
        rows = fetch_page(url, key, after)
        if not rows:
            break
        for r in rows:
            total += 1
            scraped_dt = parse_scraped(r.get("scraped"))
            q = quarter_of(scraped_dt)
            if not q:
                continue

            raw_date = r.get("date")
            if raw_date and len(str(raw_date)) >= 10 and str(raw_date)[4:5] == "-":
                date_source["iso"] += 1
            elif raw_date and REL_AGO.match(str(raw_date)):
                date_source["relative"] += 1
            else:
                date_source["fallback"] += 1

            desc = r.get("full_description") or r.get("description") or ""
            out = {
                "Id": next_id,
                "Date": resolve_date(raw_date, scraped_dt),
                "Job Title": r.get("job_title") or "",
                "Company": r.get("company") or "",
                "Location": r.get("location") or "",
                "Region": r.get("region") or "",
                "Function": r.get("function") or "",
                "Job Level": r.get("job_level") or "",
                "Industry": r.get("industry") or "",
                "Salary Period": r.get("salary_period") or "",
                # ~35% of the table has a salary of 0 (mostly expired listings).
                # Written blank, not 0, so the table does not show a fake GBP0.
                # The portal's stats and charts already skip non-positive values.
                "Min Salary": _sal(r.get("min_salary")),
                "Max Salary": _sal(r.get("max_salary")),
                "Job Description": desc[:DESC_MAX],
                "Dataset": DATASET_LABEL,
            }
            if out["Min Salary"] == "" and out["Max Salary"] == "":
                zero_salary += 1

            for f in FILL_BLANK:
                if not str(out[f]).strip():
                    out[f] = NOT_CLASSIFIED
                    filled[f] += 1

            next_id += 1
            counts[q] = counts.get(q, 0) + 1
            if not args.dry_run:
                shard_for(q).writerow(out)

        after = rows[-1]["id"]
        if total % 25_000 < PAGE:
            done = sum(counts.values())
            print(f"  {total:,} rows fetched, {done:,} written, "
                  f"{time.time() - t0:.0f}s", flush=True)
        if args.limit and total >= args.limit:
            break

    for h in handles.values():
        h.close()

    # Keep previously published rows that the fetch no longer has. Matched on
    # title + employer + pay, not date: a re-scraped advert comes back with a
    # later date, and keeping the old copy too would count it twice.
    kept = 0
    if previous:
        keep_key = lambda r: tuple((r.get(k) or "").strip() for k in ("Job Title", "Company", "Min Salary", "Max Salary"))
        now = set()
        for names in files_by_q.values():
            for n in names:
                with (OUT_DIR / n).open(newline="", encoding="utf-8") as f:
                    now.update(keep_key(r) for r in csv.DictReader(f))
        gone = {}
        for q, r in previous:
            if keep_key(r) not in now:
                gone.setdefault(q, []).append(r)
        for q, rows_q in gone.items():
            if q not in files_by_q:
                files_by_q[q] = [f"scraped4_{q}.csv"]
                with (OUT_DIR / files_by_q[q][0]).open("w", encoding="utf-8", newline="") as fh:
                    csv.DictWriter(fh, fieldnames=TARGET_COLS).writeheader()
            with (OUT_DIR / files_by_q[q][-1]).open("a", encoding="utf-8", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=TARGET_COLS, extrasaction="ignore")
                for r in rows_q:
                    r["Id"] = next_id
                    next_id += 1
                    w.writerow(r)
            counts[q] = counts.get(q, 0) + len(rows_q)
            kept += len(rows_q)

    print(f"\nFetched {total:,} rows in {time.time() - t0:.0f}s")
    if previous:
        print(f"Kept {kept:,} previously published rows no longer in Supabase")
    print("\nRows per quarter:")
    for q in sorted(counts):
        names = files_by_q.get(q, [])
        size = sum((OUT_DIR / n).stat().st_size for n in names) if names else 0
        print(f"  {q}: {counts[q]:>8,} rows  {size/1024/1024:6.1f} MB  {names}")

    print("\nDate resolution:")
    for k, v in date_source.items():
        print(f"  {k:9s} {v:7,}  {100*v/max(total,1):5.1f}%")

    print(f"\nRows with no usable salary (written blank): {zero_salary:,} "
          f"({100*zero_salary/max(total,1):.1f}%)")
    print(f'\nBlanks filled with "{NOT_CLASSIFIED}":')
    for f, n in filled.items():
        print(f"  {f:15s} {n:7,}  {100*n/max(total,1):5.1f}%")

    if args.dry_run:
        print("\nDRY RUN: no files written.")
        return 0

    # Merge into quarters.json, tagging every entry with its dataset.
    idx_path = OUT_DIR / "quarters.json"
    index = json.loads(idx_path.read_text())
    entries = [e for e in index["quarters"] if e.get("dataset") != DATASET_LABEL]
    for e in entries:
        e.setdefault("dataset", MAIN_LABEL)
    for q in sorted(counts):
        names = files_by_q[q]
        entries.append({
            "id": f"{DATASET_LABEL}:{q}",
            "quarter": q,
            "dataset": DATASET_LABEL,
            "rows": counts[q],
            "files": names,
            "bytes": sum((OUT_DIR / n).stat().st_size for n in names),
        })

    def sort_key(e):
        q = e.get("quarter") or e["id"]
        try:
            y, n = q.split("Q")
            base = (int(y), int(n))
        except Exception:
            base = (0, 0)
        return (e.get("dataset") != MAIN_LABEL, -base[0], -base[1])

    entries.sort(key=sort_key)
    index["quarters"] = entries
    idx_path.write_text(json.dumps(index, indent=2), encoding="utf-8")

    grand = sum(e["rows"] for e in entries)
    print(f"\nquarters.json updated: {len(entries)} entries, {grand:,} rows total.")
    if not args.no_builder:
        from builder_sync import sync
        sync("scraped4")
    return 0


if __name__ == "__main__":
    sys.exit(main())
