import hashlib
import os
from pathlib import Path

from ..db.engine import get_connection
from ..config import config
from .parsers import parse_file
from .chunker import chunk_text
from .embedder import create_embedder
from .vector_store import create_vector_store
from ..db.structured_data import import_data_file


def _file_hash(file_path: Path) -> str:
    """Compute a quick hash of a file (first 8KB + size)."""
    size = file_path.stat().st_size
    with open(file_path, "rb") as f:
        head = f.read(8192)
    return hashlib.sha256(head + str(size).encode()).hexdigest()[:16]


def scan_resources():
    """Scan resources/ for new or modified files, parse and store them."""
    config.ensure_dirs()
    embedder = create_embedder()
    vector_store = create_vector_store()
    conn = get_connection()

    try:
        # Ensure the file_registry table exists
        conn.execute("""
            CREATE TABLE IF NOT EXISTS file_registry (
                path TEXT PRIMARY KEY, mtime REAL NOT NULL, hash TEXT NOT NULL,
                file_size INTEGER DEFAULT 0, file_type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                error_msg TEXT, processed_at TEXT
            )
        """)
        conn.commit()

        # Scan all files in resources
        resources = Path(config.RESOURCES_DIR)
        if not resources.exists():
            return []

        results = []
        for file_path in sorted(resources.rglob("*")):
            if not file_path.is_file():
                continue
            if file_path.name.startswith("."):
                continue

            stat = file_path.stat()
            fhash = _file_hash(file_path)

            # Check registry
            row = conn.execute(
                "SELECT hash, status FROM file_registry WHERE path = ?",
                (str(file_path),),
            ).fetchone()
            if row and row["hash"] == fhash and row["status"] == "processed":
                continue

            # Parse file
            text_content, file_type = parse_file(file_path)
            now_ts = os.path.getmtime(file_path)

            if file_type == "text" and text_content:
                # Chunk, embed, store in vector DB
                chunks = chunk_text(text_content)
                if chunks:
                    ids = [f"{file_path.stem}_{i}" for i in range(len(chunks))]
                    metadatas = [
                        {"source": str(file_path), "chunk": i}
                        for i in range(len(chunks))
                    ]
                    vector_store.add_texts(ids, chunks, metadatas)

                conn.execute(
                    """INSERT OR REPLACE INTO file_registry
                       (path, mtime, hash, file_size, file_type, status, processed_at)
                       VALUES (?, ?, ?, ?, ?, 'processed', datetime('now'))""",
                    (str(file_path), now_ts, fhash, stat.st_size, file_type),
                )

            elif file_type == "data":
                # Import to SQLite
                try:
                    result = import_data_file(file_path)
                    status = "processed"
                except Exception as e:
                    status = f"error: {e}"

                conn.execute(
                    """INSERT OR REPLACE INTO file_registry
                       (path, mtime, hash, file_size, file_type, status, processed_at)
                       VALUES (?, ?, ?, ?, ?, ?, datetime('now'))""",
                    (str(file_path), now_ts, fhash, stat.st_size, file_type, status),
                )

            conn.commit()
            results.append({"path": str(file_path), "type": file_type})

        return results
    finally:
        conn.close()
