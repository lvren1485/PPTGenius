# Large Spreadsheet Summary

## Problem

Spreadsheets with >30 cells currently output raw `CREATE TABLE + INSERT` SQL text. The LLM
cannot execute SQL — it must "read" thousands of INSERT rows and do mental math. This is
unreliable for aggregation, filtering, or statistical reasoning.

## Approach

For spreadsheets exceeding the small threshold (row_count × col_count > 30), instead of
SQL DDL/DML, generate a **comprehensive Markdown statistical summary**. The summary is
treated as regular document text — chunked and BM25-indexed alongside other knowledge files.

## Summary Content

| Section | Content |
|---|---|
| **Sheet title** | Original sheet name |
| **Dimensions** | rows × cols, data density (% non-null) |
| **Column profile** | Per column: name, dtype, null count, null% |
| **Numeric stats** | Per numeric column: min, max, mean, median, std, variance, Q1, Q3, skew |
| **Categorical stats** | Per non-numeric column: unique count, top-10 values with counts & % |
| **Data preview** | First 50 rows as Markdown table |

## Code Changes

```
spreadsheet_parser.py                                       # modify _sheet_to_sql → _sheet_to_summary
  _sheet_to_summary(df, sheet_name) → str                   # generate Markdown summary
  _column_profile(df) → dict                                # dtype / null stats per column
  _numeric_stats(series) → dict                             # min/max/mean/median/std/var/Q1/Q3/skew
  _categorical_stats(series) → dict                         # unique count, top-10 frequencies
  _data_preview(df) → str                                   # first 50 rows as MD table
```

Changes are **entirely within spreadsheet_parser.py**. No new models, no new repositories,
no changes to the RAG pipeline. The output is plain Markdown text ingested via the existing
`parse → chunk → BM25 → search` flow.

## File Count

1 file changed: `spreadsheet_parser.py` (~150 lines added, ~60 lines removed for old SQL code)
