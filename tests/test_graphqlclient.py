"""Tests for the GraphQL client plugin — saved requests CRUD, resolve target, format helpers."""

import json
import uuid

import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI

from backend.plugins.graphqlclient_plugin import (
    GraphQLClientPlugin,
    _resolve_target,
    _format_type_ref,
    INTROSPECTION_QUERY,
)
from backend.plugins.storage_plugin import get_db
from tests.conftest import auth_headers


@pytest.fixture
def app():
    app = FastAPI()
    plugin = GraphQLClientPlugin.__new__(GraphQLClientPlugin)
    plugin.router = __import__("fastapi", fromlist=["APIRouter"]).APIRouter()
    plugin._register_routes()
    app.include_router(plugin.router, prefix="/api/graphqlclient")
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


# ---------- Helper function tests ----------


class TestResolveTarget:
    def test_direct_url(self, db):
        result = _resolve_target(target_url="http://localhost:4000/graphql")
        assert result["url"] == "http://localhost:4000/graphql"
        assert "Content-Type" in result["headers"]

    def test_extra_headers_merge(self, db):
        result = _resolve_target(
            target_url="http://localhost/graphql",
            extra_headers={"X-Custom": "val"},
        )
        assert result["headers"]["X-Custom"] == "val"
        assert result["headers"]["Content-Type"] == "application/json"

    def test_environment_resolution(self, db):
        """Create an environment and verify _resolve_target uses it."""
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        env_id = str(uuid.uuid4())
        db.execute(
            "INSERT INTO environments (id, name, base_url, graphql_path, verify_ssl, "
            "headers_json, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
            (env_id, "test", "https://api.example.com", "/v1/graphql", 1,
             '{"X-Env": "production"}', now, now),
        )
        db.commit()

        result = _resolve_target(env_id=env_id)
        assert result["url"] == "https://api.example.com/v1/graphql"
        assert result["headers"]["X-Env"] == "production"
        assert result["verify_ssl"] is True

    def test_env_with_trailing_slash(self, db):
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        env_id = str(uuid.uuid4())
        db.execute(
            "INSERT INTO environments (id, name, base_url, graphql_path, "
            "created_at, updated_at) VALUES (?,?,?,?,?,?)",
            (env_id, "slash", "https://api.example.com/", "/graphql", now, now),
        )
        db.commit()

        result = _resolve_target(env_id=env_id)
        assert result["url"] == "https://api.example.com/graphql"

    def test_missing_env(self, db):
        result = _resolve_target(env_id="nonexistent", target_url="http://fallback/gql")
        assert result["url"] == "http://fallback/gql"

    def test_verify_ssl_false(self, db):
        result = _resolve_target(target_url="http://x", verify_ssl=False)
        assert result["verify_ssl"] is False


class TestFormatTypeRef:
    def test_named_type(self):
        assert _format_type_ref({"kind": "SCALAR", "name": "String", "ofType": None}) == "String"

    def test_non_null(self):
        ref = {"kind": "NON_NULL", "name": None, "ofType": {"kind": "SCALAR", "name": "Int", "ofType": None}}
        assert _format_type_ref(ref) == "Int!"

    def test_list(self):
        ref = {"kind": "LIST", "name": None, "ofType": {"kind": "SCALAR", "name": "String", "ofType": None}}
        assert _format_type_ref(ref) == "[String]"

    def test_non_null_list(self):
        ref = {
            "kind": "NON_NULL",
            "name": None,
            "ofType": {
                "kind": "LIST",
                "name": None,
                "ofType": {"kind": "SCALAR", "name": "ID", "ofType": None},
            },
        }
        assert _format_type_ref(ref) == "[ID]!"

    def test_empty(self):
        assert _format_type_ref(None) == "Unknown"
        assert _format_type_ref({}) == "Unknown"


class TestIntrospectionQuery:
    def test_query_defined(self):
        assert "IntrospectionQuery" in INTROSPECTION_QUERY
        assert "__schema" in INTROSPECTION_QUERY


# ---------- Saved requests CRUD ----------


class TestSavedRequestsCRUD:
    def _create_request(self, client, admin_token, name="Test Request"):
        resp = client.post(
            "/api/graphqlclient/requests/save",
            json={
                "name": name,
                "query": "{ users { id name } }",
                "variables_json": '{"limit": 10}',
                "headers_json": "{}",
                "description": "Test query",
            },
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 200
        return resp.json()["id"]

    def test_create_request(self, client, admin_token, db):
        req_id = self._create_request(client, admin_token)
        assert req_id

    def test_list_requests(self, client, admin_token, db):
        self._create_request(client, admin_token, "List Test 1")
        self._create_request(client, admin_token, "List Test 2")

        resp = client.get(
            "/api/graphqlclient/requests/list",
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 200
        requests = resp.json()["requests"]
        assert len(requests) >= 2
        names = [r["name"] for r in requests]
        assert "List Test 1" in names
        assert "List Test 2" in names

    def test_get_request(self, client, admin_token, db):
        req_id = self._create_request(client, admin_token, "Get Test")

        resp = client.get(
            f"/api/graphqlclient/requests/{req_id}",
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Get Test"
        assert data["query"] == "{ users { id name } }"
        # JSON fields should be parsed
        assert isinstance(data["variables_json"], dict)
        assert data["variables_json"]["limit"] == 10

    def test_update_request(self, client, admin_token, db):
        req_id = self._create_request(client, admin_token, "Update Me")

        resp = client.post(
            "/api/graphqlclient/requests/save",
            json={
                "id": req_id,
                "name": "Updated",
                "query": "{ posts { id } }",
                "variables_json": "{}",
                "headers_json": "{}",
            },
            headers=auth_headers(admin_token),
        )
        assert resp.json()["status"] == "updated"

        data = client.get(
            f"/api/graphqlclient/requests/{req_id}",
            headers=auth_headers(admin_token),
        ).json()
        assert data["name"] == "Updated"
        assert data["query"] == "{ posts { id } }"

    def test_delete_request(self, client, admin_token, db):
        req_id = self._create_request(client, admin_token, "Delete Me")

        resp = client.delete(
            f"/api/graphqlclient/requests/{req_id}",
            headers=auth_headers(admin_token),
        )
        assert resp.json()["status"] == "deleted"

        resp = client.get(
            f"/api/graphqlclient/requests/{req_id}",
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 404

    def test_delete_nonexistent(self, client, admin_token, db):
        resp = client.delete(
            f"/api/graphqlclient/requests/{uuid.uuid4()}",
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 404


class TestSavedRequestsValidation:
    def test_empty_name_rejected(self, client, admin_token, db):
        resp = client.post(
            "/api/graphqlclient/requests/save",
            json={"name": "   ", "query": "{ x }"},
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 400

    def test_invalid_variables_json(self, client, admin_token, db):
        resp = client.post(
            "/api/graphqlclient/requests/save",
            json={
                "name": "Bad Vars",
                "query": "{ x }",
                "variables_json": "not-json",
                "headers_json": "{}",
            },
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 400

    def test_invalid_headers_json(self, client, admin_token, db):
        resp = client.post(
            "/api/graphqlclient/requests/save",
            json={
                "name": "Bad Hdrs",
                "query": "{ x }",
                "variables_json": "{}",
                "headers_json": "{invalid}",
            },
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 400


# ---------- Execute endpoint validation ----------


class TestExecuteValidation:
    def test_empty_query_rejected(self, client, admin_token, db):
        resp = client.post(
            "/api/graphqlclient/execute",
            json={"query": "   "},
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 400

    def test_no_target_url(self, client, admin_token, db):
        resp = client.post(
            "/api/graphqlclient/execute",
            json={"query": "{ hello }"},
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 400

    def test_execute_requires_auth(self, client, db):
        resp = client.post(
            "/api/graphqlclient/execute",
            json={"query": "{ hello }", "target_url": "http://localhost"},
        )
        assert resp.status_code == 401


# ---------- Import from config ----------


class TestImportFromConfig:
    def test_import_operations(self, client, admin_token, db):
        # Create a test config with operations
        config_id = str(uuid.uuid4())
        now = "2025-01-01T00:00:00Z"
        config_json = json.dumps({
            "operations": [
                {
                    "name": "GetUsers",
                    "type": "query",
                    "query": "{ users { id } }",
                    "enabled": True,
                    "variables": [{"name": "limit", "value": "10"}],
                },
                {
                    "name": "CreatePost",
                    "type": "mutation",
                    "query": "mutation { createPost(input: {}) { id } }",
                    "enabled": True,
                    "variables": [],
                },
            ],
            "global_params": {"timeout": 30},
        })
        db.execute(
            "INSERT INTO test_configs (id, name, config_json, created_at, updated_at) VALUES (?,?,?,?,?)",
            (config_id, "My Config", config_json, now, now),
        )
        db.commit()

        resp = client.get(
            f"/api/graphqlclient/from-config/{config_id}",
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["config_name"] == "My Config"
        assert len(data["operations"]) == 2
        assert data["operations"][0]["name"] == "GetUsers"
        assert data["operations"][1]["name"] == "CreatePost"
        assert data["global_params"]["timeout"] == 30

    def test_import_nonexistent_config(self, client, admin_token, db):
        resp = client.get(
            f"/api/graphqlclient/from-config/{uuid.uuid4()}",
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 404


# ---------- RBAC tests ----------


class TestGraphQLClientRBAC:
    def test_list_requires_auth(self, client):
        resp = client.get("/api/graphqlclient/requests/list")
        assert resp.status_code == 401

    def test_save_requires_maintainer(self, client, reader_token, db):
        resp = client.post(
            "/api/graphqlclient/requests/save",
            json={"name": "X", "query": "{ x }"},
            headers=auth_headers(reader_token),
        )
        assert resp.status_code == 403

    def test_delete_requires_maintainer(self, client, reader_token, db):
        resp = client.delete(
            f"/api/graphqlclient/requests/{uuid.uuid4()}",
            headers=auth_headers(reader_token),
        )
        assert resp.status_code == 403
