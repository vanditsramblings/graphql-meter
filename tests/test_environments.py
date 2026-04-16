"""Tests for the environments plugin — CRUD, TLS config, cert types."""

import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.plugins.environments_plugin import (
    CERT_TYPES,
    EnvironmentsPlugin,
    _decrypt_cert_password,
    _encrypt_cert_password,
)
from tests.conftest import auth_headers


@pytest.fixture
def app():
    app = FastAPI()
    plugin = EnvironmentsPlugin.__new__(EnvironmentsPlugin)
    plugin.router = __import__("fastapi", fromlist=["APIRouter"]).APIRouter()
    plugin._register_routes()
    app.include_router(plugin.router, prefix="/api/environments")
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


# ---------- Cert type / TLS mode metadata ----------


class TestCertMetadata:
    def test_list_cert_types(self, client):
        resp = client.get("/api/environments/cert-types")
        assert resp.status_code == 200
        data = resp.json()
        assert "pem" in data["cert_types"]
        assert "pfx" in data["cert_types"]
        assert any(m["value"] == "mtls" for m in data["tls_modes"])

    def test_cert_type_fields(self):
        assert "fields" in CERT_TYPES["pem"]
        pem_fields = {f["name"] for f in CERT_TYPES["pem"]["fields"]}
        assert "cert_data" in pem_fields
        assert "key_data" in pem_fields


# ---------- Cert password encryption ----------


class TestCertPasswordEncryption:
    def test_encrypt_decrypt_roundtrip(self):
        original = "my-secret-password"
        encrypted = _encrypt_cert_password(original)
        assert encrypted != original
        assert encrypted != ""
        decrypted = _decrypt_cert_password(encrypted)
        assert decrypted == original

    def test_empty_password(self):
        assert _encrypt_cert_password("") == ""
        assert _decrypt_cert_password("") == ""


# ---------- CRUD tests ----------


class TestEnvironmentCRUD:
    def test_create_environment(self, client, admin_token, db):
        resp = client.post(
            "/api/environments/save",
            json={
                "name": "test-env",
                "base_url": "https://test.example.com",
                "graphql_path": "/graphql",
                "protocol": "https",
                "tls_mode": "standard",
            },
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "created"
        assert "id" in data

    def test_list_environments(self, client, admin_token, db):
        # Create one first
        client.post(
            "/api/environments/save",
            json={"name": "list-test", "base_url": "http://localhost"},
            headers=auth_headers(admin_token),
        )
        resp = client.get(
            "/api/environments/list",
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 200
        envs = resp.json()["environments"]
        assert len(envs) >= 1
        names = [e["name"] for e in envs]
        assert "list-test" in names

    def test_get_environment(self, client, admin_token, db):
        create = client.post(
            "/api/environments/save",
            json={"name": "get-test", "base_url": "https://a.com"},
            headers=auth_headers(admin_token),
        )
        env_id = create.json()["id"]

        resp = client.get(
            f"/api/environments/{env_id}",
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "get-test"

    def test_update_environment(self, client, admin_token, db):
        create = client.post(
            "/api/environments/save",
            json={"name": "update-me", "base_url": "https://old.com"},
            headers=auth_headers(admin_token),
        )
        env_id = create.json()["id"]

        resp = client.post(
            "/api/environments/save",
            json={"id": env_id, "name": "updated", "base_url": "https://new.com"},
            headers=auth_headers(admin_token),
        )
        assert resp.json()["status"] == "updated"

        env = client.get(
            f"/api/environments/{env_id}",
            headers=auth_headers(admin_token),
        ).json()
        assert env["name"] == "updated"
        assert env["base_url"] == "https://new.com"

    def test_delete_environment(self, client, admin_token, db):
        create = client.post(
            "/api/environments/save",
            json={"name": "delete-me", "base_url": "http://x.com"},
            headers=auth_headers(admin_token),
        )
        env_id = create.json()["id"]

        resp = client.delete(
            f"/api/environments/{env_id}",
            headers=auth_headers(admin_token),
        )
        assert resp.json()["status"] == "deleted"

        resp = client.get(
            f"/api/environments/{env_id}",
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 404

    def test_delete_nonexistent(self, client, admin_token, db):
        resp = client.delete(
            f"/api/environments/{uuid.uuid4()}",
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 404


# ---------- Validation tests ----------


class TestEnvironmentValidation:
    def test_invalid_protocol(self, client, admin_token, db):
        resp = client.post(
            "/api/environments/save",
            json={"name": "bad", "base_url": "http://x", "protocol": "ftp"},
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 400

    def test_invalid_tls_mode(self, client, admin_token, db):
        resp = client.post(
            "/api/environments/save",
            json={"name": "bad", "base_url": "http://x", "tls_mode": "invalid"},
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 400

    def test_invalid_headers_json(self, client, admin_token, db):
        resp = client.post(
            "/api/environments/save",
            json={"name": "bad", "base_url": "http://x", "headers_json": "not-json"},
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 400

    def test_valid_headers_json(self, client, admin_token, db):
        resp = client.post(
            "/api/environments/save",
            json={
                "name": "hdr-test",
                "base_url": "http://x",
                "headers_json": '{"X-Custom": "val"}',
            },
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 200


# ---------- TLS/mTLS settings ----------


class TestTLSSettings:
    def test_mtls_environment(self, client, admin_token, db):
        resp = client.post(
            "/api/environments/save",
            json={
                "name": "mtls-env",
                "base_url": "https://secure.example.com",
                "protocol": "mtls",
                "tls_mode": "mtls",
                "cert_type": "pem",
                "cert_data": "MIICERT...",
                "key_data": "MIIKEY...",
                "verify_ssl": True,
            },
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 200
        env_id = resp.json()["id"]

        env = client.get(
            f"/api/environments/{env_id}",
            headers=auth_headers(admin_token),
        ).json()
        assert env["protocol"] == "mtls"
        assert env["tls_mode"] == "mtls"
        assert env["cert_type"] == "pem"

    def test_update_preserves_cert_data(self, client, admin_token, db):
        """When updating, truncated cert data should be preserved from DB."""
        create = client.post(
            "/api/environments/save",
            json={
                "name": "cert-keep",
                "base_url": "https://x.com",
                "cert_data": "A" * 200,
                "key_data": "B" * 200,
            },
            headers=auth_headers(admin_token),
        )
        env_id = create.json()["id"]

        # List truncates cert data
        envs = client.get(
            "/api/environments/list",
            headers=auth_headers(admin_token),
        ).json()["environments"]
        env = next(e for e in envs if e["id"] == env_id)
        assert "[truncated]" in env["cert_data"]

        # Update with truncated data should keep originals
        client.post(
            "/api/environments/save",
            json={
                "id": env_id,
                "name": "cert-keep-updated",
                "base_url": "https://x.com",
                "cert_data": env["cert_data"],
                "key_data": env["key_data"],
            },
            headers=auth_headers(admin_token),
        )

        # Verify original data is preserved in DB
        row = db.execute(
            "SELECT cert_data, key_data FROM environments WHERE id = ?",
            (env_id,),
        ).fetchone()
        assert row["cert_data"] == "A" * 200
        assert row["key_data"] == "B" * 200


# ---------- RBAC tests ----------


class TestEnvironmentRBAC:
    def test_list_requires_auth(self, client):
        resp = client.get("/api/environments/list")
        assert resp.status_code == 401

    def test_save_requires_maintainer(self, client, reader_token, db):
        resp = client.post(
            "/api/environments/save",
            json={"name": "blocked", "base_url": "http://x"},
            headers=auth_headers(reader_token),
        )
        assert resp.status_code == 403

    def test_delete_requires_admin(self, client, maintainer_token, admin_token, db):
        # Create with admin
        create = client.post(
            "/api/environments/save",
            json={"name": "del-test", "base_url": "http://x"},
            headers=auth_headers(admin_token),
        )
        env_id = create.json()["id"]

        # Maintainer cannot delete
        resp = client.delete(
            f"/api/environments/{env_id}",
            headers=auth_headers(maintainer_token),
        )
        assert resp.status_code == 403

        # Admin can delete
        resp = client.delete(
            f"/api/environments/{env_id}",
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 200
