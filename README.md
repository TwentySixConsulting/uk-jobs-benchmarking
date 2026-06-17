# UK Jobs Benchmarking

Static benchmarking dashboard for the full UK jobs dataset scraped by TwentySix Consulting. Forked from `housing-association-benchmarking` with the data swapped for the whole-population scrape and a new quarter-by-quarter loader so the browser doesn't have to swallow 1.6 M rows at once.

Live (after GitHub Pages is enabled): https://twentysixconsulting.github.io/uk-jobs-benchmarking/

## How it works

- The source CSV (`processed_scraped_data2026.csv`, ~2.6 GB, 1.6 M rows) is split into one CSV per `year_quarter` value by `build_quarters.py`.
- Each quarter file is sharded if larger than 80 MB so every file stays under GitHub's 100 MB serving limit.
- `quarters/quarters.json` is the manifest the front-end reads. It lists each quarter, its row count, and the file(s) to fetch.
- On first load the page fetches only the most recent quarter. Older quarters appear as checkboxes in the sidebar — tick to load on demand, untick to drop.
- Filters, stats, charts, table and CSV export are unchanged from the housing site.

## Rebuilding the data

When a fresh scrape lands in `…/Scraping 2.0/Processed Data 2026/processed_scraped_data2026.csv`:

```bash
cd /Users/millieharrison/uk-jobs-benchmarking
python3 build_quarters.py
git add quarters/ && git commit -m "Refresh quarter data" && git push
```

The script streams the source (no full load into memory) and overwrites the contents of `quarters/`.

If the source path moves, edit the `SOURCE` constant near the top of `build_quarters.py`.

## Running locally

```bash
python3 -m http.server 8000
open http://localhost:8000
```

## File layout

```
build_quarters.py     # one-shot data splitter — re-run after each scrape
index.html            # single-page dashboard, fetches quarters/* on demand
quarters/
  quarters.json       # manifest, newest quarter first
  2026Q2.csv          # single-file quarter
  2025Q1_a.csv        # multi-shard quarter
  2025Q1_b.csv
  2025Q1_c.csv
  ...
```
