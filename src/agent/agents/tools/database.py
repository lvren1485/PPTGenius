"""Tools for querying and managing structured data (CSV/XLSX imports)."""

from .registry import register
from ...db.structured_data import query_table, import_data_file, list_tables


@register
def query_database(sql: str) -> dict:
    """Execute a SQL query against the structured data database.

    Args:
        sql: A valid SQL SELECT query.

    Returns:
        Dict with 'columns' and 'rows' keys, or 'error' on failure.
    """
    return query_table(sql)


@register
def create_database(file_path: str, table_name: str | None = None) -> dict:
    """Import a CSV or XLSX file as a SQLite table for querying.

    Args:
        file_path: Path to the CSV or XLSX file.
        table_name: Optional custom table name (defaults to filename stem).

    Returns:
        Dict with table_name, row_count, and columns.
    """
    return import_data_file(file_path, table_name)
