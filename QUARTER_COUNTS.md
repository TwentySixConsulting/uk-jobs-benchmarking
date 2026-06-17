# Quarter row counts

Source file: `processed_scraped_data2026.csv` (1,613,501 rows).
Generated 2026-06-17 by `build_quarters.py`. 3,863 duplicate `job_id` rows were dropped during dedup, leaving **1,609,638 rows** total across the eight quarters.

| Quarter | Rows | Files on disk |
| --- | ---: | --- |
| 2026Q2 | 1,555 | `2026Q2.csv` |
| 2026Q1 | 66,899 | `2026Q1.csv` |
| 2025Q4 | 64,374 | `2025Q4.csv` |
| 2025Q3 | 155,569 | `2025Q3.csv` |
| 2025Q2 | 331,030 | `2025Q2_a.csv`, `2025Q2_b.csv` |
| 2025Q1 | 539,791 | `2025Q1_a.csv`, `2025Q1_b.csv`, `2025Q1_c.csv` |
| 2024Q4 | 362,993 | `2024Q4_a.csv`, `2024Q4_b.csv` |
| 2024Q3 | 87,427 | `2024Q3.csv` |
| **TOTAL** | **1,609,638** | |

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

3. The same CSVs were parsed with a PapaParse-equivalent parser in Node (the same library the dashboard uses in the browser) and produced identical counts.

> **Why `wc -l` gives bigger numbers.** Job Description fields contain literal newlines, and `wc -l` counts every newline as a separate line — including the ones inside quoted CSV fields. A proper CSV parser (and PapaParse in the browser) treats those as part of one row, which is why the actual row counts match the manifest.

## What the dashboard shows

The header counter shows three things:

- **`N records`** — the number of rows currently passing all sidebar filters (this is the number that changes as you type in the Job Title box or untick a checklist value).
- **`loaded: M`** — total rows currently in memory (sum of all ticked quarters in the sidebar). On first page load this is 1,555 (just 2026Q2).
- **`total available across all quarters: 1,609,638`** — the grand total you'd have if you ticked every quarter.

When **no filters are narrowed**, the first two numbers are equal — e.g. `1,555 records · loaded: 1,555 (2026Q2)`. Tick another quarter and both numbers increase by exactly that quarter's row count from the table above.
