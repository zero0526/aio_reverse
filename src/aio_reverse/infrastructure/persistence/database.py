"""SQLite connection manager with WAL mode, foreign keys, and context management."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator
from aio_reverse.infrastructure.persistence.schema import init_schema


class DatabaseManager:
    """Manages SQLite connection lifecycle and optimization pragmas."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._ensure_db_directory()

    def _ensure_db_directory(self) -> None:
        """Ensures the parent directory for SQLite file exists."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager yielding a configured SQLite connection.
        
        Applies:
        - WAL (Write-Ahead Logging) for high concurrency
        - NORMAL synchronous mode for balanced safety and throughput
        - ON foreign keys for referential integrity
        - sqlite3.Row factory for dictionary-style access
        """
        conn = sqlite3.connect(
            str(self.db_path),
            timeout=30.0,
            detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
        )
        conn.row_factory = sqlite3.Row

        # Performance and integrity pragmas
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA busy_timeout = 5000;")

        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize(self) -> None:
        """Initializes tables and indexes."""
        with self.get_connection() as conn:
            init_schema(conn)
