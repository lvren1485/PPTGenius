from pathlib import Path


def parse_data_file(file_path: str | Path) -> str:
    """Parse data files (CSV, XLSX) - returns a summary for the registry.

    Actual import to SQLite is handled by db.structured_data.
    This just returns a text summary for logging purposes.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Data file not found: {path}")

    import pandas as pd

    ext = path.suffix.lower()
    if ext == ".csv":
        df = pd.read_csv(path)
    else:
        df = pd.read_excel(path)

    info = (
        f"File: {path.name}\n"
        f"Rows: {len(df)}\n"
        f"Columns: {', '.join(str(c) for c in df.columns)}\n"
        f"Types: {', '.join(f'{c}: {df[c].dtype}' for c in df.columns)}\n"
    )
    return info
