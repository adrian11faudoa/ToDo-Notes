"""
database/connection.py
─────────────────────
Thread-safe SQLite connection manager.
Uses WAL journal mode for concurrent read performance.
All queries go through here — never import sqlite3 directly elsewhere.
"""

import sqlite3
import threading
import os
import logging
from pathlib import Path
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class DatabaseManager:
    """
    Singleton database manager.
    Provides thread-local connections so each thread gets its own
    SQLite handle (SQLite is not safe to share across threads).
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
        return cls._instance

    def initialize(self, db_path: str):
        """Call once at startup with the database file path."""
        if self._initialized:
            return
        self._db_path = db_path
        self._thread_local = threading.local()
        self._initialized = True

        # Run schema on the main thread connection
        with self.get_connection() as conn:
            self._apply_schema(conn)
            self._run_migrations(conn)
        logger.info(f"Database initialized at {db_path}")

    def _apply_schema(self, conn: sqlite3.Connection):
        """Execute the schema SQL file on first run."""
        schema_path = Path(__file__).parent / "schema.sql"
        if schema_path.exists():
            sql = schema_path.read_text(encoding="utf-8")
            # Split by statement-ending semicolons but skip FTS-trigger blocks
            conn.executescript(sql)
            conn.commit()

    def _run_migrations(self, conn: sqlite3.Connection):
        """
        Lightweight migration system.
        Each migration is a (version, sql) tuple; runs once and records.
        """
        conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        # Future migrations go here as (version_int, sql_string) tuples
        migrations = []
        applied = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}
        for version, sql in migrations:
            if version not in applied:
                conn.executescript(sql)
                conn.execute("INSERT INTO schema_migrations (version) VALUES (?)", (version,))
                conn.commit()
                logger.info(f"Applied migration v{version}")

    def _get_thread_connection(self) -> sqlite3.Connection:
        """Return (creating if needed) a connection for the current thread."""
        if not hasattr(self._thread_local, "conn") or self._thread_local.conn is None:
            conn = sqlite3.connect(
                self._db_path,
                detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
                check_same_thread=False,
            )
            conn.row_factory = sqlite3.Row          # dict-like rows
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA cache_size=-32000")  # 32 MB page cache
            conn.execute("PRAGMA temp_store=MEMORY")
            self._thread_local.conn = conn
        return self._thread_local.conn

    @contextmanager
    def get_connection(self):
        """
        Context manager that yields a live connection.
        Does NOT auto-commit — caller decides when to commit.
        """
        conn = self._get_thread_connection()
        try:
            yield conn
        except Exception:
            conn.rollback()
            raise

    @contextmanager
    def transaction(self):
        """
        Context manager for explicit transactions.
        Commits on success, rolls back on exception.
        """
        conn = self._get_thread_connection()
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Transaction rolled back: {e}")
            raise

    def execute(self, sql: str, params=()) -> sqlite3.Cursor:
        """Execute a single statement (no transaction)."""
        conn = self._get_thread_connection()
        return conn.execute(sql, params)

    def executemany(self, sql: str, params_seq) -> sqlite3.Cursor:
        """Execute a statement with multiple param sets."""
        conn = self._get_thread_connection()
        return conn.executemany(sql, params_seq)

    def fetchall(self, sql: str, params=()) -> list[sqlite3.Row]:
        """Execute and return all rows as sqlite3.Row objects."""
        return self.execute(sql, params).fetchall()

    def fetchone(self, sql: str, params=()) -> sqlite3.Row | None:
        """Execute and return a single row or None."""
        return self.execute(sql, params).fetchone()

    def commit(self):
        """Commit pending changes on the current thread's connection."""
        self._get_thread_connection().commit()

    def close_thread_connection(self):
        """Close and discard the current thread's connection."""
        if hasattr(self._thread_local, "conn") and self._thread_local.conn:
            self._thread_local.conn.close()
            self._thread_local.conn = None

    def vacuum(self):
        """Reclaim unused space (run during idle time)."""
        with self.get_connection() as conn:
            conn.execute("VACUUM")

    def backup(self, backup_path: str):
        """Create a hot backup to backup_path."""
        src = self._get_thread_connection()
        dest = sqlite3.connect(backup_path)
        src.backup(dest)
        dest.close()
        logger.info(f"Database backed up to {backup_path}")


# Module-level singleton
db = DatabaseManager()
