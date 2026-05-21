import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .engine import get_connection
from ..config import config


def infer_sql_type(dtype: str) -> str:
    """Map pandas dtype to SQLite type."""
    if "int" in dtype:
        return "INTEGER"
    if "float" in dtype:
        return "REAL"
    return "TEXT"


def import_data_file(file_path: str | Path, table_name: str | None = None) -> dict:
    """Import a CSV or XLSX file into a SQLite table.

    Returns metadata about the import.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    # Read with pandas
    ext = path.suffix.lower()
    if ext == ".csv":
        df = pd.read_csv(path)
    elif ext in (".xls", ".xlsx"):
        df = pd.read_excel(path)
    else:
        raise ValueError(f"Unsupported file type: {ext}")

    # Auto-generate table name from filename if not provided
    if table_name is None:
        table_name = path.stem.replace(" ", "_").replace("-", "_")

    conn = get_connection()
    try:
        df.to_sql(table_name, conn, if_exists="replace", index=False)
        row_count = len(df)
        columns = json.dumps([
            {"name": col, "type": infer_sql_type(str(df[col].dtype))}
            for col in df.columns
        ])
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """INSERT OR REPLACE INTO _imports
               (table_name, source_file, imported_at, row_count, columns)
               VALUES (?, ?, ?, ?, ?)""",
            (table_name, str(path), now, row_count, columns),
        )
        conn.commit()
        return {"table_name": table_name, "row_count": row_count, "columns": columns}
    finally:
        conn.close()


def get_table_info(table_name: str) -> dict | None:
    """Get metadata about an imported table."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM _imports WHERE table_name = ?", (table_name,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_tables() -> list[dict]:
    """List all imported data tables."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM _imports ORDER BY imported_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def query_table(sql: str) -> dict:
    """Execute a SQL query against the structured database.

    Returns columns and rows.
    """
    conn = get_connection()
    try:
        cursor = conn.execute(sql)
        columns = [desc[0] for desc in cursor.description]
        rows = [list(row) for row in cursor.fetchall()]
        return {"columns": columns, "rows": rows}
    except Exception as e:
        return {"error": str(e), "columns": [], "rows": []}
    finally:
        conn.close()
