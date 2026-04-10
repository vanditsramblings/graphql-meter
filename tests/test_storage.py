"""Tests for the storage plugin — database init, migrations, metadata CRUD."""

import sqlite3
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI

from backend.plugins.storage_plugin import get_db, _init_tables, _migrate_schema
from tests.conftest import auth_headers


# ---------- Database initialization tests ----------


class TestDatabaseInit:
    """Verify tables and schema are created properly."""

    def test_all_tables_exist(self, db):
        tables = {
            row[0]
            for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        expected = {
            "metadata",
            "test_configs",
            "test_runs",
            "operation_results",
            "cleanup_jobs",
            "environments",
            "graphql_requests",
            "auth_providers",
        }
        assert expected.issubset(tables), f"Missing tables: {expected - tables}"

    def test_environments_has_new_columns(self, db):
        cursor = db.execute("PRAGMA table_info(environments)")
        cols = {row[1] for row in cursor.fetchall()}
        new_cols = {
            "protocol",
            "tls_mode",
            "cert_type",
            "cert_data",
            "key_data",
            "cert_password_encrypted",
            "ca_cert_data",
            "verify_ssl",
            "headers_json",
            "auth_provider_id",
        }
        assert new_cols.issubset(cols), f"Missing columns: {new_cols - cols}"

    def test_graphql_requests_table_schema(self, db):
        cursor = db.execute("PRAGMA table_info(graphql_requests)")
        cols = {row[1] for row in cursor.fetchall()}
        assert "query" in cols
        assert "variables_json" in cols
        assert "environment_id" in cols

    def test_wal_mode(self, db):
        mode = db.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal"


class TestMigration:
    """Verify incremental migration on existing databases."""

    def test_migrate_adds_missing_columns(self, tmp_path):
        """Simulate an old DB missing new environment columns."""
        db_path = str(tmp_path / "migrate_test.db")
        conn = sqlite3.connect(db_path)
        conn.execute(
            "CREATE TABLE environments (id TEXT PRIMARY KEY, name TEXT, platform TEXT, "
            "base_url TEXT, graphql_path TEXT, cert_path TEXT, key_path TEXT, notes TEXT, "
            "created_at TEXT, updated_at TEXT)"
        )
        conn.commit()

        _migrate_schema(conn)

        cursor = conn.execute("PRAGMA table_info(environments)")
        cols = {row[1] for row in cursor.fetchall()}
        assert "protocol" in cols
        assert "tls_mode" in cols
        assert "verify_ssl" in cols
        assert "auth_provider_id" in cols
        conn.close()


# ---------- Metadata endpoint tests ----------


class TestMetadataEndpoints:
    """Test the /api/storage/metadata CRUD."""

    @pytest.fixture
    def app(self):
        from backend.plugins.storage_plugin import StoragePlugin

        app = FastAPI()
        plugin = StoragePlugin.__new__(StoragePlugin)
        # Skip __init__ to avoid re-initializing DB
        plugin.router = __import__("fastapi", fromlist=["APIRouter"]).APIRouter()
        plugin._register_routes()
        app.include_router(plugin.router, prefix="/api/storage")
        return app

    @pytest.fixture
    def client(self, app):
        return TestClient(app)

    def test_get_metadata_not_found(self, client):
        resp = client.get("/api/storage/metadata/nonexistent")
        assert resp.status_code == 404

    def test_set_and_get_metadata(self, client):
        resp = client.put(
            "/api/storage/metadata/test_key",
            json={"value": "hello"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "saved"

        resp = client.get("/api/storage/metadata/test_key")
        assert resp.status_code == 200
        assert resp.json()["value"] == "hello"

    def test_update_metadata(self, client):
        client.put("/api/storage/metadata/k", json={"value": "v1"})
        client.put("/api/storage/metadata/k", json={"value": "v2"})
        resp = client.get("/api/storage/metadata/k")
        assert resp.json()["value"] == "v2"

    def test_storage_status(self, client):
        resp = client.get("/api/storage/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "test_configs" in data
