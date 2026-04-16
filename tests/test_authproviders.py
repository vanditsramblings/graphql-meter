"""Tests for the auth providers plugin — encryption, CRUD, token caching."""


import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.plugins.authproviders_plugin import (
    AUTH_TYPE_FIELDS,
    AuthProvidersPlugin,
    _decrypt,
    _encrypt,
    _mask,
    _mask_config,
    _token_cache,
    clear_token_cache,
    get_auth_header,
    get_cached_auth_header,
)
from tests.conftest import auth_headers


@pytest.fixture
def app():
    app = FastAPI()
    plugin = AuthProvidersPlugin.__new__(AuthProvidersPlugin)
    plugin.router = __import__("fastapi", fromlist=["APIRouter"]).APIRouter()
    plugin._register_routes()
    app.include_router(plugin.router, prefix="/api/authproviders")
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_cache():
    """Clear token cache between tests."""
    clear_token_cache()
    yield
    clear_token_cache()


# ---------- Encryption tests ----------


class TestEncryption:
    def test_encrypt_decrypt_roundtrip(self):
        plaintext = "super-secret-value"
        encrypted = _encrypt(plaintext)
        assert encrypted != plaintext
        decrypted = _decrypt(encrypted)
        assert decrypted == plaintext

    def test_different_plaintexts_different_ciphertext(self):
        enc1 = _encrypt("value1")
        enc2 = _encrypt("value2")
        assert enc1 != enc2

    def test_encrypt_empty_string(self):
        enc = _encrypt("")
        assert _decrypt(enc) == ""

    def test_encrypt_unicode(self):
        text = "héllo wörld 🔑"
        assert _decrypt(_encrypt(text)) == text


class TestMasking:
    def test_mask_long_string(self):
        result = _mask("abcdefghij")
        assert result.startswith("abcd")
        assert "****" in result

    def test_mask_short_string(self):
        assert _mask("ab") == "****"
        assert _mask("") == "****"

    def test_mask_config(self):
        config = {
            "token": "my-secret-token",
            "username": "myuser",
            "password": "mypass",
        }
        masked = _mask_config(config)
        assert masked["username"] == "myuser"  # not sensitive
        assert "****" in masked["token"]
        assert "****" in masked["password"]
        assert "my-secret-token" not in masked["token"]


# ---------- Auth type schema tests ----------


class TestAuthTypeSchemas:
    def test_all_types_defined(self):
        expected_types = {
            "bearer_token",
            "basic",
            "api_key",
            "oauth2_client_credentials",
            "oauth2_password",
            "jwt_custom",
        }
        assert set(AUTH_TYPE_FIELDS.keys()) == expected_types

    def test_each_type_has_fields(self):
        for type_name, schema in AUTH_TYPE_FIELDS.items():
            assert "label" in schema, f"{type_name} missing label"
            assert "fields" in schema, f"{type_name} missing fields"
            assert len(schema["fields"]) > 0, f"{type_name} has no fields"

    def test_required_fields_marked(self):
        # bearer_token should have 'token' as required
        token_fields = AUTH_TYPE_FIELDS["bearer_token"]["fields"]
        token_field = next(f for f in token_fields if f["name"] == "token")
        assert token_field["required"] is True


# ---------- CRUD endpoint tests ----------


class TestAuthProviderCRUD:
    def _create_bearer(self, client, admin_token):
        resp = client.post(
            "/api/authproviders/save",
            json={
                "name": "Test Bearer",
                "auth_type": "bearer_token",
                "config": {"token": "my-test-token"},
                "description": "Test bearer provider",
            },
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 200
        return resp.json()["id"]

    def test_create_bearer_token(self, client, admin_token, db):
        provider_id = self._create_bearer(client, admin_token)
        assert provider_id

    def test_list_providers(self, client, admin_token, db):
        self._create_bearer(client, admin_token)
        resp = client.get(
            "/api/authproviders/list",
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 200
        providers = resp.json()["providers"]
        assert len(providers) >= 1
        # List should NOT contain config_encrypted
        for p in providers:
            assert "config_encrypted" not in p

    def test_get_provider_masked(self, client, admin_token, db):
        provider_id = self._create_bearer(client, admin_token)
        resp = client.get(
            f"/api/authproviders/{provider_id}",
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Test Bearer"
        assert "config" in data
        assert "config_encrypted" not in data
        # Token should be masked
        assert "****" in data["config"]["token"]
        assert "my-test-token" not in data["config"]["token"]

    def test_update_provider_preserves_masked_secrets(self, client, admin_token, db):
        provider_id = self._create_bearer(client, admin_token)

        # Get the masked version
        existing = client.get(
            f"/api/authproviders/{provider_id}",
            headers=auth_headers(admin_token),
        ).json()

        # Update with masked token — should keep original
        client.post(
            "/api/authproviders/save",
            json={
                "id": provider_id,
                "name": "Updated Bearer",
                "auth_type": "bearer_token",
                "config": {"token": existing["config"]["token"]},
            },
            headers=auth_headers(admin_token),
        )

        # Verify the underlying data still has original token
        headers = get_auth_header(provider_id)
        assert headers is not None
        assert headers["Authorization"] == "Bearer my-test-token"

    def test_delete_provider(self, client, admin_token, db):
        provider_id = self._create_bearer(client, admin_token)
        resp = client.delete(
            f"/api/authproviders/{provider_id}",
            headers=auth_headers(admin_token),
        )
        assert resp.json()["status"] == "deleted"

        resp = client.get(
            f"/api/authproviders/{provider_id}",
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 404

    def test_create_basic_auth(self, client, admin_token, db):
        resp = client.post(
            "/api/authproviders/save",
            json={
                "name": "Basic Provider",
                "auth_type": "basic",
                "config": {"username": "user", "password": "pass"},
            },
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 200
        provider_id = resp.json()["id"]

        headers = get_auth_header(provider_id)
        assert "Authorization" in headers
        assert headers["Authorization"].startswith("Basic ")

    def test_create_api_key(self, client, admin_token, db):
        resp = client.post(
            "/api/authproviders/save",
            json={
                "name": "API Key Provider",
                "auth_type": "api_key",
                "config": {"header_name": "X-API-Key", "api_key": "secret-key"},
            },
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 200
        provider_id = resp.json()["id"]

        headers = get_auth_header(provider_id)
        assert headers["X-API-Key"] == "secret-key"

    def test_invalid_auth_type(self, client, admin_token, db):
        resp = client.post(
            "/api/authproviders/save",
            json={
                "name": "Bad Type",
                "auth_type": "nonexistent",
                "config": {},
            },
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 400

    def test_missing_required_fields(self, client, admin_token, db):
        resp = client.post(
            "/api/authproviders/save",
            json={
                "name": "Missing Token",
                "auth_type": "bearer_token",
                "config": {},
            },
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 400


# ---------- Validation & test endpoint ----------


class TestAuthProviderTest:
    def test_test_bearer_success(self, client, admin_token, db):
        resp = client.post(
            "/api/authproviders/test",
            json={"auth_type": "bearer_token", "config": {"token": "abc"}},
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_test_bearer_empty(self, client, admin_token, db):
        resp = client.post(
            "/api/authproviders/test",
            json={"auth_type": "bearer_token", "config": {"token": ""}},
            headers=auth_headers(admin_token),
        )
        data = resp.json()
        assert data["success"] is False

    def test_test_basic_success(self, client, admin_token, db):
        resp = client.post(
            "/api/authproviders/test",
            json={"auth_type": "basic", "config": {"username": "u", "password": "p"}},
            headers=auth_headers(admin_token),
        )
        assert resp.json()["success"] is True

    def test_test_api_key_success(self, client, admin_token, db):
        resp = client.post(
            "/api/authproviders/test",
            json={
                "auth_type": "api_key",
                "config": {"header_name": "X-Key", "api_key": "val"},
            },
            headers=auth_headers(admin_token),
        )
        assert resp.json()["success"] is True

    def test_test_invalid_type(self, client, admin_token, db):
        resp = client.post(
            "/api/authproviders/test",
            json={"auth_type": "nope", "config": {}},
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 400


# ---------- Token resolution tests ----------


class TestAuthHeaderResolution:
    def test_bearer_token_header(self, client, admin_token, db):
        resp = client.post(
            "/api/authproviders/save",
            json={
                "name": "Resolve Test",
                "auth_type": "bearer_token",
                "config": {"token": "tok-123"},
            },
            headers=auth_headers(admin_token),
        )
        pid = resp.json()["id"]
        headers = get_auth_header(pid)
        assert headers == {"Authorization": "Bearer tok-123"}

    def test_nonexistent_provider(self):
        assert get_auth_header("no-such-id") is None

    def test_resolve_headers_endpoint(self, client, admin_token, db):
        resp = client.post(
            "/api/authproviders/save",
            json={
                "name": "Headers Test",
                "auth_type": "bearer_token",
                "config": {"token": "tok-456"},
            },
            headers=auth_headers(admin_token),
        )
        pid = resp.json()["id"]

        resp = client.get(
            f"/api/authproviders/{pid}/headers",
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 200
        # Should return masked headers
        assert "****" in resp.json()["headers"]["Authorization"]


# ---------- Token cache tests ----------


class TestTokenCache:
    def test_cache_stores_and_returns(self, client, admin_token, db):
        resp = client.post(
            "/api/authproviders/save",
            json={
                "name": "Cache Test",
                "auth_type": "bearer_token",
                "config": {"token": "cached-tok"},
            },
            headers=auth_headers(admin_token),
        )
        pid = resp.json()["id"]

        # First call populates cache
        h1 = get_cached_auth_header(pid)
        assert h1 == {"Authorization": "Bearer cached-tok"}

        # Second call should use cache
        h2 = get_cached_auth_header(pid)
        assert h2 == h1

    def test_clear_cache_single(self, client, admin_token, db):
        resp = client.post(
            "/api/authproviders/save",
            json={
                "name": "C1",
                "auth_type": "bearer_token",
                "config": {"token": "t1"},
            },
            headers=auth_headers(admin_token),
        )
        pid = resp.json()["id"]
        get_cached_auth_header(pid)
        assert pid in _token_cache

        clear_token_cache(pid)
        assert pid not in _token_cache

    def test_clear_cache_all(self, client, admin_token, db):
        for name in ("A", "B"):
            resp = client.post(
                "/api/authproviders/save",
                json={
                    "name": name,
                    "auth_type": "bearer_token",
                    "config": {"token": f"tok-{name}"},
                },
                headers=auth_headers(admin_token),
            )
            get_cached_auth_header(resp.json()["id"])

        assert len(_token_cache) >= 2
        clear_token_cache()
        assert len(_token_cache) == 0


# ---------- RBAC tests ----------


class TestAuthProviderRBAC:
    def test_list_requires_auth(self, client):
        resp = client.get("/api/authproviders/list")
        assert resp.status_code == 401

    def test_save_requires_maintainer(self, client, reader_token, db):
        resp = client.post(
            "/api/authproviders/save",
            json={
                "name": "X",
                "auth_type": "bearer_token",
                "config": {"token": "x"},
            },
            headers=auth_headers(reader_token),
        )
        assert resp.status_code == 403

    def test_delete_requires_admin(self, client, maintainer_token, admin_token, db):
        create = client.post(
            "/api/authproviders/save",
            json={
                "name": "Del",
                "auth_type": "bearer_token",
                "config": {"token": "x"},
            },
            headers=auth_headers(admin_token),
        )
        pid = create.json()["id"]

        # Maintainer cannot delete
        resp = client.delete(
            f"/api/authproviders/{pid}",
            headers=auth_headers(maintainer_token),
        )
        assert resp.status_code == 403

    def test_types_endpoint_public(self, client):
        resp = client.get("/api/authproviders/types")
        assert resp.status_code == 200
