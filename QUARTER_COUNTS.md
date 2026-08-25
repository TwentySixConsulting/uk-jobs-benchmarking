# Quarter row counts

Last updated 2026-08-25 by `add_new_quarters.py`, which added the 17 Jun, 1 Jul,
17 Aug and 24 Aug scrapes: **8,956 rows** across 2026Q2 (1,685) and a new 2026Q3
(7,271). Nothing existing was rewritten. Total is now **1,618,594 rows** across
9 quarters.

The original build was generated 2026-06-17 by `build_quarters.py` from a source CSV
of 1,613,501 rows, giving 1,609,638 rows after dropping 3,863 duplicate `job_id`s.
That source has since been regenerated and is now smaller than what is published
here, so `build_quarters.py` must not be re-run. See README.md.

| Quarter | Rows | Files on disk |
| --- | ---: | --- |
| 2026Q3 | 7,271 | `2026Q3.csv` |
| 2026Q2 | 3,240 | `2026Q2.csv` |
| 2026Q1 | 66,899 | `2026Q1.csv` |
| 2025Q4 | 64,374 | `2025Q4.csv` |
| 2025Q3 | 155,569 | `2025Q3.csv` |
| 2025Q2 | 331,030 | `2025Q2_a.csv`, `2025Q2_b.csv` |
| 2025Q1 | 539,791 | `2025Q1_a.csv`, `2025Q1_b.csv`, `2025Q1_c.csv` |
| 2024Q4 | 362,993 | `2024Q4_a.csv`, `2024Q4_b.csv` |
| 2024Q3 | 87,427 | `2024Q3.csv` |
| **TOTAL** | **1,618,594** | |

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

3. After the 2026-08-25 top-up, all 13 files were re-parsed: 1,618,594 rows, Ids 1-1,618,594 with no gaps and no duplicates, every row 13 columns wide.

4. The same CSVs were parsed with a PapaParse-equivalent parser in Node (the same library the dashboard uses in the browser) and produced identical counts.

> **Why `wc -l` gives bigger numbers.** Job Description fields contain literal newlines, and `wc -l` counts every newline as a separate line — including the ones inside quoted CSV fields. A proper CSV parser (and PapaParse in the browser) treats those as part of one row, which is why the actual row counts match the manifest.

## What the dashboard shows

The header counter shows three things:

- **`N records`** — the number of rows currently passing all sidebar filters (this is the number that changes as you type in the Job Title box or untick a checklist value).
- **`loaded: M`** — total rows currently in memory (sum of all ticked quarters in the sidebar). On first page load this is 7,271 (just 2026Q3).
- **`total available across all quarters: 1,618,594`** — the grand total you'd have if you ticked every quarter.

When **no filters are narrowed**, the first two numbers are equal — e.g. `7,271 records · loaded: 7,271 (2026Q3)`. Tick another quarter and both numbers increase by exactly that quarter's row count from the table above.
