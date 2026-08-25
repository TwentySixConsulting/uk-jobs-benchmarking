# UK Jobs Benchmarking

Static benchmarking dashboard for the full UK jobs dataset scraped by TwentySix Consulting. Forked from `housing-association-benchmarking` with the data swapped for the whole-population scrape and a new quarter-by-quarter loader so the browser doesn't have to swallow 1.6 M rows at once.

Live (after GitHub Pages is enabled): https://twentysixconsulting.github.io/uk-jobs-benchmarking/

## How it works

- The source CSV (`processed_scraped_data2026.csv`, ~2.6 GB, 1.6 M rows) is split into one CSV per `year_quarter` value by `build_quarters.py`.
- Each quarter file is sharded if larger than 80 MB so every file stays under GitHub's 100 MB serving limit.
- `quarters/quarters.json` is the manifest the front-end reads. It lists each quarter, its row count, and the file(s) to fetch.
- On first load the page fetches only the most recent quarter. Older quarters appear as checkboxes in the sidebar — tick to load on demand, untick to drop.
- Filters, stats, charts, table and CSV export are unchanged from the housing site.

## Updating the data

**Use `add_new_quarters.py`. Do not run `build_quarters.py` any more.**

When a fresh scrape lands in `…/Scraping 2.0/Processed Data 2026/processed_scraped_data2026.csv`:

```bash
cd uk-jobs-benchmarking
python3 add_new_quarters.py --dry-run    # see what would be added
python3 add_new_quarters.py              # add it
git add quarters/ quarters/quarters.json && git commit -m "Add new quarter data" && git push
```

`add_new_quarters.py` only ever appends. It reads the source rows for the quarters
listed in its `QUARTERS` constant, drops any it already has, and adds the rest with
Ids continuing from the highest already published. It backs up every file it touches
to `.quarters_backup/` first, then rewrites `quarters.json` from what is on disk.

Edit the `QUARTERS` list at the top of the script when a new quarter starts.

### Why `build_quarters.py` is no longer safe

It rebuilds every quarter from scratch. The source CSV was regenerated on 2026-07-01
and came out **smaller** than what is already published here (1,251,109 rows in the
source against 1,609,638 in `quarters/`), because that rebuild deduplicated across a
different set of pickle files. Older scrape data now exists only in this repo. Running
`build_quarters.py` would overwrite `quarters/` with the smaller set and lose roughly
360,000 rows permanently.

The script is kept for reference only. If you ever do need a genuine full rebuild,
copy `quarters/` somewhere safe first.

## Running locally

```bash
python3 -m http.server 8000
open http://localhost:8000
```

## File layout

```
add_new_quarters.py   # additive top-up — run this after each scrape
build_quarters.py     # ORIGINAL full rebuild — do not run, it would lose data
index.html            # single-page dashboard, fetches quarters/* on demand
quarters/
  quarters.json       # manifest, newest quarter first
  2026Q2.csv          # single-file quarter
  2025Q1_a.csv        # multi-shard quarter
  2025Q1_b.csv
  2025Q1_c.csv
  ...
```
