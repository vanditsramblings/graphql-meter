"""Shared test fixtures for backend unit tests."""

import sqlite3
import time

import pytest

# Override DB_PATH before any backend imports
_test_db_fd = None
_test_db_path = None


@pytest.fixture(autouse=True)
def _patch_db(tmp_path, monkeypatch):
    """Redirect the database to a temp file for every test."""
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("DB_PATH", db_path)
    monkeypatch.setenv("JWT_SECRET", "test-secret-key-for-unit-tests-1234567890")
    monkeypatch.setenv("ENCRYPTION_KEY", "test-encryption-key-1234567890abcdef")

    # Reset cached settings so each test uses fresh env vars
    from backend import config as _cfg
    monkeypatch.setattr(_cfg, "get_settings", lambda: _cfg.Settings())

    # Reset storage module globals
    import backend.plugins.storage_plugin as _sp
    _sp._db_path = db_path
    # Clear thread-local connection
    if hasattr(_sp._local, "conn"):
        try:
            _sp._local.conn.close()
        except Exception:
            pass
        _sp._local.conn = None

    # Reset Fernet instance so it re-derives from the test key
    import backend.plugins.authproviders_plugin as _ap
    _ap._fernet_instance = None

    # Initialize tables
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    _sp._init_tables(conn)
    conn.close()

    yield db_path

    # Cleanup thread-local
    if hasattr(_sp._local, "conn") and _sp._local.conn:
        try:
            _sp._local.conn.close()
        except Exception:
            pass
        _sp._local.conn = None


@pytest.fixture
def db():
    """Return a thread-local DB connection for direct SQL assertions."""
    from backend.plugins.storage_plugin import get_db
    return get_db()


@pytest.fixture
def admin_token():
    """Generate a valid admin JWT token for authenticated requests."""
    from backend.config import get_settings
    from backend.plugins.auth_plugin import _create_jwt
    settings = get_settings()
    payload = {
        "sub": "admin",
        "role": "admin",
        "name": "Admin",
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
    }
    return _create_jwt(payload, settings.JWT_SECRET)


@pytest.fixture
def maintainer_token():
    """Generate a valid maintainer JWT token."""
    from backend.config import get_settings
    from backend.plugins.auth_plugin import _create_jwt
    settings = get_settings()
    payload = {
        "sub": "maintainer",
        "role": "maintainer",
        "name": "Maintainer",
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
    }
    return _create_jwt(payload, settings.JWT_SECRET)


@pytest.fixture
def reader_token():
    """Generate a valid reader JWT token."""
    from backend.config import get_settings
    from backend.plugins.auth_plugin import _create_jwt
    settings = get_settings()
    payload = {
        "sub": "reader",
        "role": "reader",
        "name": "Reader",
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
    }
    return _create_jwt(payload, settings.JWT_SECRET)


def auth_headers(token: str) -> dict:
    """Build Authorization header dict."""
    return {"Authorization": f"Bearer {token}"}
