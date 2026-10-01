# UK Jobs Benchmarking

Static benchmarking dashboard for the full UK jobs dataset scraped by TwentySix Consulting. Forked from `housing-association-benchmarking` with the data swapped for the whole-population scrape and a new quarter-by-quarter loader so the browser doesn't have to swallow 1.6 M rows at once.

Live (after GitHub Pages is enabled): https://twentysixconsulting.github.io/uk-jobs-benchmarking/

## Two tabs

The page opens on **October 2026, Modelled Dataset** (tab 1), which loads all of its
325,615 rows straight away from `modelled/`. **All UK Jobs** (tab 2) is the original
portal (Main scrape + Scraped4 from `quarters/`), unchanged, and is only fetched when
someone clicks it. Each tab keeps its own filters, sort and hidden rows. Job Level is
hidden on tab 1 because the modelled file has no job levels.

### Rebuilding the modelled dataset

```bash
python3 build_modelled.py --dry-run   # counts only
python3 build_modelled.py             # rewrites modelled/ from ~/df_325k_final_run_10_26.csv
python3 build_modelled.py --source path/to/new_export.csv
```

It only ever touches `modelled/`, never `quarters/`. Dates are resolved the same way as
scraped4 (relative "3 days ago" text against the scrape timestamp), and Ids run 1..N
within the tab, separate from tab 2. To rename the tab, change `DATASET_LABEL` in the
script and the `TABS` label in `index.html`.

## How it works (All UK Jobs tab)

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

## The second dataset (scraped4)

The portal now carries two datasets, tagged in a `Dataset` column:

| Dataset | Rows | Source |
| --- | ---: | --- |
| Main scrape | 1,618,594 | `processed_scraped_data2026.csv` via `add_new_quarters.py` |
| Scraped4 | 268,810 | Supabase table `twentysix_scraped4` via `build_scraped4.py` |
| **Total** | **1,887,404** | |

Scraped4 files are named `scraped4_<quarter>.csv` and listed in `quarters.json`
with `"dataset": "Scraped4"`. They load only when ticked in the sidebar, which is
grouped by dataset. The first page load still fetches the newest main-scrape
quarter, so nobody pays for the big files unless they ask for them.

To refresh it:

```bash
python3 build_scraped4.py --dry-run
python3 build_scraped4.py
```

It reads Supabase credentials from `twentysix-salary-portal-v2/.env.local` and
rewrites only the `scraped4_*` files, then merges its entries into
`quarters.json`. Main-scrape files are never touched.

### What is different about scraped4 data

It comes from a different model and is missing most classification codes:

- `Job Level` is **100% empty**, `Function` 98.6% empty, `Industry` 96.8% empty
- 34.7% of rows have a salary of 0 (mostly expired listings). These are written
  blank, not 0, so the table does not display a fake figure. The stats and charts
  already require `Min Salary > 0`, so they are excluded from every average.
- `Salary Period` is often the literal string `unresolvable`
- The source `date` column is 63% relative text ("2 days ago"), 24% ISO
  timestamps and 13% null, so dates are resolved against the scrape timestamp.
  "N days left" is a closing date, not a posting date, and is not used.

Empty values in `Function`, `Job Level`, `Industry`, `Region` and `Salary Period`
are shown as **"Not classified"** rather than left blank. This is required, not
cosmetic: `applyFilters` tests `filters[field].has(row[field])` against a value
set built from non-blank values only, so a genuinely blank cell makes the entire
row invisible. Normalising happens in `index.html` as each row is parsed, so no
CSV needed rewriting — and it also restored the ~10,343 main-scrape rows with a
blank Region that had been silently hidden.

## Running locally

```bash
python3 -m http.server 8000
open http://localhost:8000
```

## File layout

```
add_new_quarters.py   # additive top-up — run this after each scrape
build_scraped4.py     # pulls the twentysix_scraped4 Supabase table
build_modelled.py     # builds modelled/ (tab 1) from the refined export
build_quarters.py     # ORIGINAL full rebuild — do not run, it would lose data
index.html            # single-page dashboard, two tabs, fetches CSVs on demand
modelled/             # tab 1: same layout as quarters/
  quarters.json
  modelled_2026Q3_a.csv
  ...
quarters/
  quarters.json       # manifest, newest quarter first
  2026Q2.csv          # single-file quarter
  2025Q1_a.csv        # multi-shard quarter
  2025Q1_b.csv
  2025Q1_c.csv
  ...
```
