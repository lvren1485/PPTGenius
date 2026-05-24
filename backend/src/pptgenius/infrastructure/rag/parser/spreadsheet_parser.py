"""CSV / XLSX parser.

- ≤ 30 cells → Markdown table (LLM can read directly)
- > 30 cells → SQL (LLM can query / compute via SQL)
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from .base import ParsedDocument

_SMALL_THRESHOLD = 30  # row_count × col_count


# -- markdown output ---------------------------------------------------------

def _sheet_to_markdown(df: pd.DataFrame, sheet_name: str) -> str:
    df = df.dropna(how="all").dropna(axis=1, how="all")
    if df.empty:
        return f"## Sheet: {sheet_name}\n\n_(empty sheet)_"
    df = df.fillna("").map(lambda x: str(x).strip() if isinstance(x, str) else x)

    lines = [f"## Sheet: {sheet_name}", ""]
    headers = [str(c) for c in df.columns]
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for _, row in df.iterrows():
        cells = [str(v) for v in row]
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    return "\n".join(lines)


import numpy as np

# -- SQL output --------------------------------------------------------------

def _sanitise_name(name: str) -> str:
    """Turn a sheet name into a valid SQL table name."""
    name = re.sub(r"[^\w]", "_", name)
    name = re.sub(r"_+", "_", name).strip("_").lower()
    return name or "sheet"


def _infer_sql_type(series: pd.Series) -> str:
    """Guess the SQL column type from a pandas Series."""
    if pd.api.types.is_integer_dtype(series):
        return "INTEGER"
    if pd.api.types.is_float_dtype(series):
        return "REAL"
    if pd.api.types.is_bool_dtype(series):
        return "INTEGER"  # SQLite has no BOOLEAN
    return "TEXT"


def _sheet_to_sql(df: pd.DataFrame, sheet_name: str) -> str:
    """Dump a DataFrame as CREATE TABLE + INSERT statements."""
    df = df.dropna(how="all").dropna(axis=1, how="all")
    if df.empty:
        return f"-- Sheet: {sheet_name} (empty)"

    table = _sanitise_name(sheet_name)
    cols = [str(c) for c in df.columns]
    col_defs: list[str] = []
    for col in cols:
        sql_type = _infer_sql_type(df[col])
        col_defs.append(f'    "{col}" {sql_type}')

    lines = [
        f"-- Sheet: {sheet_name}  (rows={len(df)}, cols={len(cols)})",
        f"CREATE TABLE {table} (",
        ",\n".join(col_defs),
        ");",
        "",
    ]

    # Batch INSERTs so the text doesn't become a single gigantic line
    values_lines: list[str] = []
    for _, row in df.iterrows():
        vals = []
        for col in cols:
            v = row[col]
            if pd.isna(v) or v == "":
                vals.append("NULL")
            elif isinstance(v, (int, float, np.integer, np.floating)):
                vals.append(str(v))
            else:
                escaped = str(v).replace("'", "''")
                vals.append(f"'{escaped}'")
        values_lines.append(f"({', '.join(vals)})")

    # Emit in chunks of 500 rows
    chunk_size = 500
    for i in range(0, len(values_lines), chunk_size):
        chunk = values_lines[i:i + chunk_size]
        prefix = "INSERT INTO " if i == 0 else "-- continue\nINSERT INTO "
        lines.append(f"{prefix}{table} VALUES")
        lines.append(",\n".join(chunk) + ";")
        lines.append("")

    return "\n".join(lines)


# -- public API --------------------------------------------------------------

def parse_spreadsheet(file_path: str | Path) -> ParsedDocument:
    """Read .csv / .xlsx → Markdown (small) or SQL (large) per sheet."""
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix == ".csv":
        df = pd.read_csv(path, encoding="utf-8-sig")
        sheets = [(path.stem, df)]
    elif suffix in (".xlsx", ".xls"):
        xl = pd.ExcelFile(path, engine="openpyxl")
        sheets = [(name, pd.read_excel(path, sheet_name=name)) for name in xl.sheet_names]
        xl.close()
    else:
        raise ValueError(f"unsupported spreadsheet format: {suffix}")

    parts: list[str] = []
    total_cells = 0
    for name, df in sheets:
        cells = len(df) * len(df.columns)
        total_cells += cells
        if cells <= _SMALL_THRESHOLD:
            parts.append(_sheet_to_markdown(df, name))
        else:
            parts.append(_sheet_to_sql(df, name))

    return ParsedDocument(
        file_path=str(path),
        file_type=suffix.lstrip("."),
        text="\n".join(parts),
        metadata={
            "filename": path.name,
            "sheets": len(sheets),
            "total_cells": total_cells,
        },
    )
