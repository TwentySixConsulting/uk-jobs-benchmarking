# Quarter row counts

Last updated 2026-08-25. The portal now carries **two datasets**, distinguished by
a `Dataset` column: the main scrape (1,618,594 rows) and
scraped4 (268,810 rows, from the Supabase table
`twentysix_scraped4`). Total **1,887,404 rows**.

Scraped4 quarters are separate files and load only when ticked. The main-scrape
files were not modified when scraped4 was added.

| Quarter | Dataset | Rows | Files on disk |
| --- | --- | ---: | --- |
| 2026Q3 | Main scrape | 7,271 | `2026Q3.csv` |
| 2026Q2 | Main scrape | 3,240 | `2026Q2.csv` |
| 2026Q1 | Main scrape | 66,899 | `2026Q1.csv` |
| 2025Q4 | Main scrape | 64,374 | `2025Q4.csv` |
| 2025Q3 | Main scrape | 155,569 | `2025Q3.csv` |
| 2025Q2 | Main scrape | 331,030 | `2025Q2_a.csv`, `2025Q2_b.csv` |
| 2025Q1 | Main scrape | 539,791 | `2025Q1_a.csv`, `2025Q1_b.csv`, `2025Q1_c.csv` |
| 2024Q4 | Main scrape | 362,993 | `2024Q4_a.csv`, `2024Q4_b.csv` |
| 2024Q3 | Main scrape | 87,427 | `2024Q3.csv` |
| 2026Q3 | Scraped4 | 184,937 | `scraped4_2026Q3.csv` |
| 2026Q2 | Scraped4 | 83,873 | `scraped4_2026Q2.csv` |
| **TOTAL** | | **1,887,404** | |

`build_quarters.py` must not be re-run; see README.md. The source CSV is now
smaller than what is published here.

## Verifying the counts

Two independent counts agree:

1. **Build log output** — number of rows written to each per-quarter CSV during `build_quarters.py`.
2. **Re-parsing the CSVs** with Python's `csv` module after the build:

   ```
   Quarter    Manifest    Re-parsed    Diff
   2026Q2        1,555        1,555       0
   2026Q1       66,899       66,899       0
   2025Q4       64,374       64,374       0
   2025Q3      155,569      155,569       0
   2025Q2      331,030      331,030       0
   2025Q1      539,791      539,791       0
   2024Q4      362,993      362,993       0
   2024Q3       87,427       87,427       0
   TOTAL    1,609,638    1,609,638       0
   ```

3. After adding scraped4 on 2026-08-25, all 15 files were re-parsed: 1,887,404 rows, Ids 1-1,887,404 with no gaps and no duplicates. Main-scrape files are 13 columns, scraped4 files 14 (the extra one is `Dataset`).

4. The same CSVs were parsed with a PapaParse-equivalent parser in Node (the same library the dashboard uses in the browser) and produced identical counts.

> **Why `wc -l` gives bigger numbers.** Job Description fields contain literal newlines, and `wc -l` counts every newline as a separate line — including the ones inside quoted CSV fields. A proper CSV parser (and PapaParse in the browser) treats those as part of one row, which is why the actual row counts match the manifest.

## What the dashboard shows

The header counter shows three things:

- **`N records`** — the number of rows currently passing all sidebar filters (this is the number that changes as you type in the Job Title box or untick a checklist value).
- **`loaded: M`** — total rows currently in memory (sum of all ticked quarters in the sidebar). On first page load this is 7,271 (just 2026Q3).
- **`total available across all quarters: 1,887,404`** — the grand total you'd have if you ticked every quarter.

When **no filters are narrowed**, the first two numbers are equal — e.g. `7,271 records · loaded: 7,271 (2026Q3)`. Tick another quarter and both numbers increase by exactly that quarter's row count from the table above.
