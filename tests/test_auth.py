"""Tests for the auth plugin — login, JWT, RBAC, feature flags."""

import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.config import get_settings
from backend.plugins.auth_plugin import (
    AuthPlugin,
    _create_jwt,
    _decode_jwt,
    get_flags_for_role,
    has_role,
)

# ---------- JWT helper tests ----------


class TestJWT:
    def test_create_and_decode(self):
        secret = get_settings().JWT_SECRET
        payload = {"sub": "user1", "role": "admin", "exp": int(time.time()) + 3600}
        token = _create_jwt(payload, secret)
        decoded = _decode_jwt(token, secret)
        assert decoded is not None
        assert decoded["sub"] == "user1"
        assert decoded["role"] == "admin"

    def test_expired_token(self):
        secret = get_settings().JWT_SECRET
        payload = {"sub": "user1", "role": "admin", "exp": int(time.time()) - 10}
        token = _create_jwt(payload, secret)
        assert _decode_jwt(token, secret) is None

    def test_invalid_signature(self):
        secret = get_settings().JWT_SECRET
        payload = {"sub": "user1", "role": "admin", "exp": int(time.time()) + 3600}
        token = _create_jwt(payload, secret)
        # Tamper with payload
        parts = token.split(".")
        parts[1] = parts[1] + "x"
        tampered = ".".join(parts)
        assert _decode_jwt(tampered, secret) is None

    def test_wrong_secret(self):
        payload = {"sub": "user1", "exp": int(time.time()) + 3600}
        token = _create_jwt(payload, "secret-a")
        assert _decode_jwt(token, "secret-b") is None

    def test_malformed_token(self):
        secret = get_settings().JWT_SECRET
        assert _decode_jwt("not.a.token", secret) is None
        assert _decode_jwt("only-one-part", secret) is None
        assert _decode_jwt("", secret) is None


# ---------- Role hierarchy tests ----------


class TestRoles:
    def test_admin_has_all_roles(self):
        assert has_role("admin", "reader")
        assert has_role("admin", "maintainer")
        assert has_role("admin", "admin")

    def test_reader_limited(self):
        assert has_role("reader", "reader")
        assert not has_role("reader", "maintainer")
        assert not has_role("reader", "admin")

    def test_maintainer_intermediate(self):
        assert has_role("maintainer", "reader")
        assert has_role("maintainer", "maintainer")
        assert not has_role("maintainer", "admin")

    def test_unknown_role(self):
        assert not has_role("unknown", "reader")


# ---------- Feature flags tests ----------


class TestFeatureFlags:
    def test_admin_gets_all_flags(self):
        flags = get_flags_for_role("admin")
        assert "tests.create" in flags
        assert "storage.clear" in flags
        assert "results.export" in flags

    def test_reader_gets_subset(self):
        flags = get_flags_for_role("reader")
        assert "results.export" in flags
        assert "tests.run" in flags
        assert "tests.create" not in flags
        assert "storage.clear" not in flags

    def test_maintainer_flags(self):
        flags = get_flags_for_role("maintainer")
        assert "tests.create" in flags
        assert "configs.create" in flags
        assert "storage.clear" not in flags


# ---------- Login endpoint tests ----------


class TestLoginEndpoint:
    @pytest.fixture
    def app(self):
        app = FastAPI()
        plugin = AuthPlugin()
        app.include_router(plugin.router, prefix="/api/auth")
        return app

    @pytest.fixture
    def client(self, app):
        return TestClient(app)

    def test_login_success(self, client):
        resp = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert data["user"]["role"] == "admin"

    def test_login_wrong_password(self, client):
        resp = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "wrong"},
        )
        assert resp.status_code == 401

    def test_login_unknown_user(self, client):
        resp = client.post(
            "/api/auth/login",
            json={"username": "nobody", "password": "pass"},
        )
        assert resp.status_code == 401

    def test_login_reader(self, client):
        resp = client.post(
            "/api/auth/login",
            json={"username": "reader", "password": "reader123"},
        )
        assert resp.status_code == 200
        assert resp.json()["user"]["role"] == "reader"
