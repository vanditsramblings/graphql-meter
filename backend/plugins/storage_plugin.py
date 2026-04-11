"""Storage plugin — SQLite initialization, migrations, thread-local connections, WAL mode."""

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any

from fastapi import HTTPException

from backend.core.plugin_base import PluginBase
from backend.config import get_settings

_local = threading.local()
_db_path: Optional[str] = None


def get_db() -> sqlite3.Connection:
    """Get a thread-local SQLite connection."""
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(_db_path, check_same_thread=False)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA foreign_keys=ON")
        _local.conn.execute("PRAGMA busy_timeout=5000")
    return _local.conn


def _init_tables(conn: sqlite3.Connection):
    """Create all tables if they don't exist."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS test_configs (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            schema_text TEXT,
            config_json TEXT,
            created_by TEXT,
            created_at TEXT,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS test_runs (
            id TEXT PRIMARY KEY,
            config_id TEXT REFERENCES test_configs(id),
            name TEXT,
            status TEXT CHECK(status IN ('pending','running','completed','failed','stopped')),
            started_at TEXT,
            completed_at TEXT,
            user_count INTEGER,
            ramp_up_sec INTEGER,
            duration_sec INTEGER,
            host TEXT,
            platform TEXT,
            config_snapshot TEXT,
            summary_json TEXT,
            error_log TEXT,
            engine TEXT,
            debug_mode INTEGER DEFAULT 0,
            cleanup_on_stop INTEGER DEFAULT 0,
            notes TEXT,
            tags TEXT,
            environment_id TEXT,
            created_by TEXT
        );

        CREATE TABLE IF NOT EXISTS operation_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT REFERENCES test_runs(id),
            operation_name TEXT,
            operation_type TEXT,
            request_count INTEGER,
            failure_count INTEGER,
            avg_response_ms REAL,
            min_response_ms REAL,
            max_response_ms REAL,
            p50_response_ms REAL,
            p90_response_ms REAL,
            p95_response_ms REAL,
            p99_response_ms REAL,
            tps_actual REAL,
            tps_target REAL,
            total_response_bytes INTEGER DEFAULT 0,
            total_request_bytes INTEGER DEFAULT 0,
            avg_response_bytes REAL DEFAULT 0,
            avg_request_bytes REAL DEFAULT 0,
            stats_json TEXT
        );

        CREATE TABLE IF NOT EXISTS cleanup_jobs (
            id TEXT PRIMARY KEY,
            run_id TEXT,
            status TEXT CHECK(status IN ('pending','running','completed','failed')),
            total_ops INTEGER,
            completed_ops INTEGER DEFAULT 0,
            failed_ops INTEGER DEFAULT 0,
            error_details TEXT,
            created_at TEXT,
            completed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS environments (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            platform TEXT,
            base_url TEXT,
            graphql_path TEXT DEFAULT '/graphql',
            protocol TEXT DEFAULT 'https' CHECK(protocol IN ('http','https','mtls')),
            tls_mode TEXT DEFAULT 'standard' CHECK(tls_mode IN ('none','standard','mtls')),
            cert_type TEXT DEFAULT '' CHECK(cert_type IN ('','none','pem','pfx','cert_key')),
            cert_data TEXT DEFAULT '',
            key_data TEXT DEFAULT '',
            cert_password_encrypted TEXT DEFAULT '',
            ca_cert_data TEXT DEFAULT '',
            verify_ssl INTEGER DEFAULT 1,
            headers_json TEXT DEFAULT '{}',
            auth_provider_id TEXT DEFAULT '',
            cert_path TEXT,
            key_path TEXT,
            notes TEXT,
            created_at TEXT,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS graphql_requests (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            folder_name TEXT DEFAULT '',
            environment_id TEXT DEFAULT '',
            auth_provider_id TEXT DEFAULT '',
            query TEXT NOT NULL,
            variables_json TEXT DEFAULT '{}',
            headers_json TEXT DEFAULT '{}',
            config_id TEXT DEFAULT '',
            operation_name TEXT DEFAULT '',
            last_response_json TEXT DEFAULT '',
            created_by TEXT,
            created_at TEXT,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS auth_providers (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            auth_type TEXT NOT NULL CHECK(auth_type IN ('bearer_token','basic','api_key','oauth2_client_credentials','oauth2_password','jwt_custom')),
            config_encrypted TEXT NOT NULL,
            description TEXT,
            created_by TEXT,
            created_at TEXT,
            updated_at TEXT
        );
    """)
    conn.commit()


def _migrate_schema(conn: sqlite3.Connection):
    """Apply incremental schema migrations for existing databases."""
    cursor = conn.execute("PRAGMA table_info(environments)")
    env_cols = {row[1] for row in cursor.fetchall()}

    new_env_cols = {
        "protocol": "TEXT DEFAULT 'https'",
        "tls_mode": "TEXT DEFAULT 'standard'",
        "cert_type": "TEXT DEFAULT ''",
        "cert_data": "TEXT DEFAULT ''",
        "key_data": "TEXT DEFAULT ''",
        "cert_password_encrypted": "TEXT DEFAULT ''",
        "ca_cert_data": "TEXT DEFAULT ''",
        "verify_ssl": "INTEGER DEFAULT 1",
        "headers_json": "TEXT DEFAULT '{}'",
        "auth_provider_id": "TEXT DEFAULT ''",
    }
    for col, col_type in new_env_cols.items():
        if col not in env_cols:
            conn.execute(f"ALTER TABLE environments ADD COLUMN {col} {col_type}")

    # Migrate graphql_requests: add folder_name (table may not exist in test DBs)
    try:
        cursor = conn.execute("PRAGMA table_info(graphql_requests)")
        req_cols = {row[1] for row in cursor.fetchall()}
        if req_cols and "folder_name" not in req_cols:
            conn.execute("ALTER TABLE graphql_requests ADD COLUMN folder_name TEXT DEFAULT ''")
    except Exception:
        pass

    # Migrate operation_results: add response/request byte sizes
    try:
        cursor = conn.execute("PRAGMA table_info(operation_results)")
        op_cols = {row[1] for row in cursor.fetchall()}
        if op_cols:
            for col, col_type in {
                "total_response_bytes": "INTEGER DEFAULT 0",
                "total_request_bytes": "INTEGER DEFAULT 0",
                "avg_response_bytes": "REAL DEFAULT 0",
                "avg_request_bytes": "REAL DEFAULT 0",
            }.items():
                if col not in op_cols:
                    conn.execute(f"ALTER TABLE operation_results ADD COLUMN {col} {col_type}")
    except Exception:
        pass

    # Migrate test_runs: add chart_snapshots column for historical chart data
    try:
        cursor = conn.execute("PRAGMA table_info(test_runs)")
        run_cols = {row[1] for row in cursor.fetchall()}
        if run_cols and "chart_snapshots" not in run_cols:
            conn.execute("ALTER TABLE test_runs ADD COLUMN chart_snapshots TEXT")
    except Exception:
        pass

    conn.commit()


def _mark_orphan_runs(conn: sqlite3.Connection):
    """Mark any stale running/pending runs as failed on startup."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE test_runs SET status = 'failed', completed_at = ?, error_log = 'Server restarted — run orphaned' "
        "WHERE status IN ('running', 'pending')",
        (now,),
    )
    conn.commit()


class StoragePlugin(PluginBase):
    @property
    def name(self) -> str:
        return "storage"

    @property
    def description(self) -> str:
        return "SQLite storage — init, migrations, thread-local connections, WAL mode"

    def __init__(self):
        global _db_path
        settings = get_settings()
        _db_path = settings.DB_PATH

        # Ensure directory exists
        Path(_db_path).parent.mkdir(parents=True, exist_ok=True)

        # Initialize database
        conn = sqlite3.connect(_db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        _init_tables(conn)
        _migrate_schema(conn)
        _mark_orphan_runs(conn)
        conn.close()

        super().__init__()

    def _register_routes(self):
        @self.router.get("/status")
        async def storage_status():
            db = get_db()
            row = db.execute("SELECT COUNT(*) as cnt FROM test_configs").fetchone()
            runs_row = db.execute("SELECT COUNT(*) as cnt FROM test_runs").fetchone()
            return {
                "status": "ok",
                "db_path": _db_path,
                "test_configs": row["cnt"],
                "test_runs": runs_row["cnt"],
            }

        @self.router.get("/metadata/{key}")
        async def get_metadata(key: str):
            db = get_db()
            row = db.execute("SELECT value, updated_at FROM metadata WHERE key = ?", (key,)).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail=f"Key '{key}' not found")
            return {"key": key, "value": row["value"], "updated_at": row["updated_at"]}

        @self.router.put("/metadata/{key}")
        async def set_metadata(key: str, body: dict):
            db = get_db()
            now = datetime.now(timezone.utc).isoformat()
            db.execute(
                "INSERT INTO metadata (key, value, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
                (key, str(body.get("value", "")), now),
            )
            db.commit()
            return {"key": key, "status": "saved"}
