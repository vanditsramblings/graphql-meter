"""Tests for the test config plugin — CRUD, TPS% validation."""

import json
import uuid

import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI

from backend.plugins.testconfig_plugin import TestConfigPlugin
from backend.plugins.storage_plugin import get_db
from tests.conftest import auth_headers


@pytest.fixture
def app():
    app = FastAPI()
    plugin = TestConfigPlugin.__new__(TestConfigPlugin)
    plugin.router = __import__("fastapi", fromlist=["APIRouter"]).APIRouter()
    plugin._register_routes()
    app.include_router(plugin.router, prefix="/api/testconfig")
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


# ---------- CRUD tests ----------


class TestTestConfigCRUD:
    def _create_config(self, client, admin_token, name="Test Config", ops=None):
        if ops is None:
            ops = [
                {"name": "GetUsers", "type": "query", "query": "{ users { id } }",
                 "enabled": True, "tps_percentage": 60},
                {"name": "GetPosts", "type": "query", "query": "{ posts { id } }",
                 "enabled": True, "tps_percentage": 40},
            ]
        resp = client.post(
            "/api/testconfig/save",
            json={
                "name": name,
                "description": "A test config",
                "schema_text": "type Query { users: [User] }",
                "config_json": {
                    "operations": ops,
                    "global_params": {"host": "http://localhost:4000"},
                },
            },
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 200
        return resp.json()["id"]

    def test_create_config(self, client, admin_token, db):
        config_id = self._create_config(client, admin_token)
        assert config_id

    def test_list_configs(self, client, admin_token, db):
        self._create_config(client, admin_token, "Config A")
        self._create_config(client, admin_token, "Config B")

        resp = client.get(
            "/api/testconfig/list",
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 200
        configs = resp.json()["configs"]
        assert len(configs) >= 2
        names = [c["name"] for c in configs]
        assert "Config A" in names
        assert "Config B" in names

    def test_get_config(self, client, admin_token, db):
        config_id = self._create_config(client, admin_token, "Get Me")

        resp = client.get(
            f"/api/testconfig/{config_id}",
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Get Me"
        assert isinstance(data["config_json"], dict)
        assert len(data["config_json"]["operations"]) == 2

    def test_update_config(self, client, admin_token, db):
        config_id = self._create_config(client, admin_token, "Original")

        resp = client.post(
            "/api/testconfig/save",
            json={
                "id": config_id,
                "name": "Updated",
                "config_json": {
                    "operations": [
                        {"name": "Op1", "enabled": True, "tps_percentage": 100},
                    ],
                    "global_params": {"host": "http://new-host"},
                },
            },
            headers=auth_headers(admin_token),
        )
        assert resp.json()["status"] == "updated"

        data = client.get(
            f"/api/testconfig/{config_id}",
            headers=auth_headers(admin_token),
        ).json()
        assert data["name"] == "Updated"

    def test_delete_config(self, client, admin_token, db):
        config_id = self._create_config(client, admin_token, "Delete Me")

        resp = client.delete(
            f"/api/testconfig/{config_id}",
            headers=auth_headers(admin_token),
        )
        assert resp.json()["status"] == "deleted"

        resp = client.get(
            f"/api/testconfig/{config_id}",
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 404

    def test_delete_nonexistent(self, client, admin_token, db):
        resp = client.delete(
            f"/api/testconfig/{uuid.uuid4()}",
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 404

    def test_get_nonexistent(self, client, admin_token, db):
        resp = client.get(
            f"/api/testconfig/{uuid.uuid4()}",
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 404


# ---------- TPS% validation tests ----------


class TestTPSValidation:
    def test_tps_must_sum_to_100(self, client, admin_token, db):
        resp = client.post(
            "/api/testconfig/save",
            json={
                "name": "Bad TPS",
                "config_json": {
                    "operations": [
                        {"name": "Op1", "enabled": True, "tps_percentage": 50},
                        {"name": "Op2", "enabled": True, "tps_percentage": 30},
                    ],
                },
            },
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 400

    def test_tps_100_accepted(self, client, admin_token, db):
        resp = client.post(
            "/api/testconfig/save",
            json={
                "name": "Good TPS",
                "config_json": {
                    "operations": [
                        {"name": "Op1", "enabled": True, "tps_percentage": 70},
                        {"name": "Op2", "enabled": True, "tps_percentage": 30},
                    ],
                },
            },
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 200

    def test_disabled_ops_excluded(self, client, admin_token, db):
        """Disabled operations should not count toward TPS% total."""
        resp = client.post(
            "/api/testconfig/save",
            json={
                "name": "Disabled Ops",
                "config_json": {
                    "operations": [
                        {"name": "Op1", "enabled": True, "tps_percentage": 100},
                        {"name": "Op2", "enabled": False, "tps_percentage": 50},
                    ],
                },
            },
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 200

    def test_no_operations_allowed(self, client, admin_token, db):
        """Empty operations list should be accepted (nothing to validate)."""
        resp = client.post(
            "/api/testconfig/save",
            json={
                "name": "Empty Ops",
                "config_json": {"operations": []},
            },
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 200


# ---------- Validate endpoint ----------


class TestValidateEndpoint:
    def test_valid_config(self, client, admin_token, db):
        resp = client.post(
            "/api/testconfig/validate",
            json={
                "name": "Valid",
                "config_json": {
                    "operations": [
                        {"name": "Op1", "enabled": True, "tps_percentage": 100},
                    ],
                    "global_params": {"host": "http://localhost"},
                },
            },
            headers=auth_headers(admin_token),
        )
        data = resp.json()
        assert data["valid"] is True
        assert data["errors"] == []

    def test_missing_name(self, client, admin_token, db):
        resp = client.post(
            "/api/testconfig/validate",
            json={
                "name": "   ",
                "config_json": {
                    "operations": [{"name": "Op", "enabled": True, "tps_percentage": 100}],
                    "global_params": {"host": "http://x"},
                },
            },
            headers=auth_headers(admin_token),
        )
        data = resp.json()
        assert data["valid"] is False
        assert any("Name" in e for e in data["errors"])

    def test_missing_host(self, client, admin_token, db):
        resp = client.post(
            "/api/testconfig/validate",
            json={
                "name": "NoHost",
                "config_json": {
                    "operations": [{"name": "Op", "enabled": True, "tps_percentage": 100}],
                    "global_params": {},
                },
            },
            headers=auth_headers(admin_token),
        )
        data = resp.json()
        assert data["valid"] is False
        assert any("Host" in e for e in data["errors"])

    def test_tps_invalid(self, client, admin_token, db):
        resp = client.post(
            "/api/testconfig/validate",
            json={
                "name": "BadTPS",
                "config_json": {
                    "operations": [
                        {"name": "Op1", "enabled": True, "tps_percentage": 50},
                    ],
                    "global_params": {"host": "http://x"},
                },
            },
            headers=auth_headers(admin_token),
        )
        data = resp.json()
        assert data["valid"] is False
        assert any("TPS" in e for e in data["errors"])

    def test_no_enabled_ops_invalid(self, client, admin_token, db):
        resp = client.post(
            "/api/testconfig/validate",
            json={
                "name": "NoOps",
                "config_json": {
                    "operations": [{"name": "Op", "enabled": False, "tps_percentage": 100}],
                    "global_params": {"host": "http://x"},
                },
            },
            headers=auth_headers(admin_token),
        )
        data = resp.json()
        assert data["valid"] is False


# ---------- RBAC tests ----------


class TestTestConfigRBAC:
    def test_list_requires_auth(self, client):
        resp = client.get("/api/testconfig/list")
        assert resp.status_code == 401

    def test_save_requires_maintainer(self, client, reader_token, db):
        resp = client.post(
            "/api/testconfig/save",
            json={"name": "Blocked", "config_json": {}},
            headers=auth_headers(reader_token),
        )
        assert resp.status_code == 403

    def test_delete_requires_maintainer(self, client, reader_token, db):
        resp = client.delete(
            f"/api/testconfig/{uuid.uuid4()}",
            headers=auth_headers(reader_token),
        )
        assert resp.status_code == 403
