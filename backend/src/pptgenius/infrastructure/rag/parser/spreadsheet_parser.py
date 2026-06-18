"""CSV / XLSX parser.

- ≤ 30 cells → full Markdown table (LLM can read directly)
- > 30 cells → statistical summary + first 50 rows preview (LLM-ready Markdown)

The summary includes per-column profiles, numeric stats (min/max/mean/median/std/var/
Q1/Q3/skew), categorical top-10 frequencies, and a data preview — all as plain Markdown
that integrates with the existing BM25 → chunk → search pipeline.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .base import ParsedDocument

_SMALL_THRESHOLD = 30  # row_count × col_count
_PREVIEW_ROWS = 30


# -- markdown table (small sheets) --------------------------------------------

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


# -- statistical summary (large sheets) ---------------------------------------

def _sheet_to_summary(df: pd.DataFrame, sheet_name: str) -> str:
    """Generate a rich Markdown statistical summary for a large sheet."""
    df = df.dropna(how="all").dropna(axis=1, how="all")
    if df.empty:
        return f"## Sheet: {sheet_name}\n\n_(empty sheet)_"

    rows, cols = len(df), len(df.columns)
    total_cells = rows * cols
    non_null = int(df.notna().sum().sum())
    density = (non_null / total_cells * 100) if total_cells > 0 else 0.0
    columns = [str(c) for c in df.columns]

    parts: list[str] = []

    # ── 1. Overview ──
    parts.append(f"## Sheet: {sheet_name} (Summary)")
    parts.append("")
    parts.append("### Overview")
    parts.append("")
    parts.append(f"- **Rows:** {rows}")
    parts.append(f"- **Columns:** {cols}")
    parts.append(f"- **Total cells:** {total_cells}")
    parts.append(f"- **Density:** {density:.1f}% non-null")
    parts.append(f"- **Data types:** {_summarise_dtypes(df)}")
    parts.append("")

    # ── 2. Column Profiles ──
    parts.append("### Column Profiles")
    parts.append("")
    parts.append("| # | Column | Type | Non-Null | Null% | Unique |")
    parts.append("|---:|---|:---|:---|:---|:---|")
    for i, col in enumerate(columns):
        s = df[col]
        nn = int(s.notna().sum())
        null_pct = (rows - nn) / rows * 100 if rows > 0 else 0
        uniq = s.nunique()
        parts.append(
            f"| {i + 1} | {_escape_md(col)} | {s.dtype} "
            f"| {nn} | {null_pct:.1f}% | {uniq} |"
        )
    parts.append("")

    # ── 3. Numeric Statistics ──
    num_cols = [c for c in columns if pd.api.types.is_numeric_dtype(df[c])]
    if num_cols:
        parts.append("### Numeric Statistics")
        parts.append("")
        for col in num_cols:
            stats = _numeric_stats(df[col])
            if stats is None:
                continue
            parts.append(f"#### {_escape_md(col)} ({stats['dtype']})")
            parts.append("")
            parts.append("| Stat | Value |")
            parts.append("| --- | --- |")
            parts.append(f"| Min | {stats['min']} |")
            parts.append(f"| Max | {stats['max']} |")
            parts.append(f"| Mean | {stats['mean']} |")
            parts.append(f"| Median | {stats['median']} |")
            parts.append(f"| Std | {stats['std']} |")
            parts.append(f"| Variance | {stats['var']} |")
            parts.append(f"| Q1 (25%) | {stats['q1']} |")
            parts.append(f"| Q3 (75%) | {stats['q3']} |")
            parts.append(f"| Skewness | {stats['skew']} |")
            parts.append(f"| Sum | {stats['sum']} |")
            parts.append("")

    # ── 4. Categorical Summary ──
    cat_cols = [c for c in columns if not pd.api.types.is_numeric_dtype(df[c])]
    if cat_cols:
        parts.append("### Categorical Summary")
        parts.append("")
        for col in cat_cols:
            cs = _categorical_stats(df[col])
            if cs is None:
                continue
            parts.append(f"#### {_escape_md(col)} — {cs['unique']} unique values")
            parts.append("")
            parts.append("| Rank | Value | Count | % |")
            parts.append("| --- | --- | --- | --- |")
            for item in cs["top10"]:
                parts.append(
                    f"| {item['rank']} | {_escape_md(str(item['value']))} "
                    f"| {item['count']} | {item['pct']:.1f}% |"
                )
            parts.append("")

    # ── 5. Data Preview ──
    parts.append(f"### Data Preview (first {_PREVIEW_ROWS} rows)")
    parts.append("")
    preview = df.head(_PREVIEW_ROWS).fillna("").map(
        lambda x: str(x).strip() if isinstance(x, str) else x
    )
    headers = [str(c) for c in preview.columns]
    parts.append("| " + " | ".join(headers) + " |")
    parts.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for _, row in preview.iterrows():
        cells = [str(v) for v in row]
        parts.append("| " + " | ".join(_truncate_cell(c) for c in cells) + " |")
    parts.append("")

    return "\n".join(parts)


def _summarise_dtypes(df: pd.DataFrame) -> str:
    """Human-readable dtype summary, e.g. 'int64×3, float64×2, object×5'."""
    counts = df.dtypes.value_counts()
    return ", ".join(f"{dt} x {cnt}" for dt, cnt in counts.items())


def _numeric_stats(series: pd.Series) -> dict | None:
    """Compute a suite of descriptive statistics for a numeric column."""
    clean = series.dropna()
    if len(clean) < 2:
        return None
    q1 = float(clean.quantile(0.25))
    q3 = float(clean.quantile(0.75))
    skew = float(clean.skew()) if len(clean) >= 3 else 0.0
    return {
        "dtype": str(series.dtype),
        "min": _fmt_num(clean.min()),
        "max": _fmt_num(clean.max()),
        "mean": _fmt_num(clean.mean()),
        "median": _fmt_num(clean.median()),
        "std": _fmt_num(clean.std()),
        "var": _fmt_num(clean.var()),
        "q1": _fmt_num(q1),
        "q3": _fmt_num(q3),
        "skew": _fmt_num(skew),
        "sum": _fmt_num(clean.sum()),
    }


def _categorical_stats(series: pd.Series) -> dict | None:
    """Compute top-10 value frequencies for a categorical column."""
    clean = series.dropna()
    if len(clean) == 0:
        return None
    top = clean.value_counts().head(10)
    total = len(clean)
    top10 = [
        {
            "rank": i + 1,
            "value": v,
            "count": int(c),
            "pct": c / total * 100,
        }
        for i, (v, c) in enumerate(top.items())
    ]
    return {
        "unique": clean.nunique(),
        "top10": top10,
    }


def _data_preview(df: pd.DataFrame, n: int = _PREVIEW_ROWS) -> str:
    """Render the first N rows as a Markdown table."""
    preview = df.head(n).fillna("").map(
        lambda x: str(x).strip() if isinstance(x, str) else x
    )
    headers = [str(c) for c in preview.columns]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for _, row in preview.iterrows():
        cells = [str(v) for v in row]
        lines.append("| " + " | ".join(_truncate_cell(c) for c in cells) + " |")
    return "\n".join(lines)


def _fmt_num(v: float) -> str:
    """Format a number: integer if close, else 4 decimal places."""
    if abs(v - round(v)) < 1e-10:
        return str(round(v))
    return f"{v:.4f}"


def _truncate_cell(text: str, limit: int = 80) -> str:
    """Truncate long cell values to keep the Markdown table readable."""
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _escape_md(text: str) -> str:
    """Escape pipe characters that would break Markdown tables."""
    return str(text).replace("|", "\\|").replace("\n", " ")


# -- public API --------------------------------------------------------------

def parse_spreadsheet(file_path: str | Path) -> ParsedDocument:
    """Read .csv / .xlsx → Markdown (small) or summary (large) per sheet."""
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
            parts.append(_sheet_to_summary(df, name))

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
