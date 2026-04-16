"""GraphQL Health endpoint — a built-in mock GraphQL server for testing.

Provides a simple schema with:
  - Query: health, serviceInfo, echo

This serves as:
  1. A self-diagnostic endpoint (the app can test itself)
  2. A default target for new users to experiment with load testing
  3. A validation target for debug mode and engine testing
"""

import json
import os
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import Request
from pydantic import BaseModel

from backend import __version__ as _VERSION
from backend.core.plugin_base import PluginBase

# Simple in-memory state for the mock GraphQL server
_state = {
    "maintenance_mode": False,
    "request_count": 0,
    "start_time": time.time(),
}

# The GraphQL schema text for this endpoint
HEALTH_SCHEMA = '''type Query {
  health: HealthStatus!
  serviceInfo: ServiceInfo!
  echo(message: String!, messageInteger: Int, messageDouble: Float, messageUUID: ID, messageTime: String): EchoResponse!
}

type Mutation {
  submitTestData(input: TestDataInput!): TestDataResponse!
}

input TestDataInput {
  label: String!
  count: Int!
  score: Float!
  referenceId: ID!
  scheduledAt: String!
  active: Boolean!
}

type HealthStatus {
  status: String!
  uptime_seconds: Int!
  request_count: Int!
  maintenance_mode: Boolean!
  timestamp: String!
}

type ServiceInfo {
  name: String!
  version: String!
  environment: String!
  features: [String!]!
}

type EchoResponse {
  message: String!
  messageInteger: Int
  messageDouble: Float
  messageUUID: ID
  messageTime: String
  received_at: String!
  request_number: Int!
}

type TestDataResponse {
  id: ID!
  label: String!
  count: Int!
  score: Float!
  referenceId: ID!
  scheduledAt: String!
  active: Boolean!
  processed_at: String!
}

'''


def _resolve_query(operation_name: str, variables: dict) -> Optional[dict]:
    """Resolve a GraphQL query against the mock schema."""
    _state["request_count"] += 1
    now = datetime.now(timezone.utc).isoformat()

    if operation_name in ("health", "Health", "HealthCheck"):
        return {
            "data": {
                "health": {
                    "status": "maintenance" if _state["maintenance_mode"] else "healthy",
                    "uptime_seconds": int(time.time() - _state["start_time"]),
                    "request_count": _state["request_count"],
                    "maintenance_mode": _state["maintenance_mode"],
                    "timestamp": now,
                }
            }
        }

    if operation_name in ("serviceInfo", "ServiceInfo"):
        return {
            "data": {
                "serviceInfo": {
                    "name": "GraphQL Meter",
                    "version": _VERSION,
                    "environment": os.environ.get("ENVIRONMENT", "development"),
                    "features": ["load_testing", "schema_parsing", "auth_providers", "environments"],
                }
            }
        }

    if operation_name in ("echo", "Echo"):
        return {
            "data": {
                "echo": {
                    "message": variables.get("message", ""),
                    "messageInteger": variables.get("messageInteger"),
                    "messageDouble": variables.get("messageDouble"),
                    "messageUUID": variables.get("messageUUID"),
                    "messageTime": variables.get("messageTime"),
                    "received_at": now,
                    "request_number": _state["request_count"],
                }
            }
        }

    if operation_name in ("submitTestData", "SubmitTestData"):
        inp = variables.get("input", {})
        return {
            "data": {
                "submitTestData": {
                    "id": f"td-{_state['request_count']}",
                    "label": inp.get("label", ""),
                    "count": inp.get("count", 0),
                    "score": inp.get("score", 0.0),
                    "referenceId": inp.get("referenceId", ""),
                    "scheduledAt": inp.get("scheduledAt", ""),
                    "active": inp.get("active", True),
                    "processed_at": now,
                }
            }
        }

    # Fallback: try to parse the query text itself for operation detection
    return None


def _parse_query_text(query: str) -> Optional[str]:
    """Extract the operation name from a GraphQL query string."""
    import re
    # Match: query OperationName or { health { ... }}
    # Check for named operation
    m = re.search(r'(?:query|mutation)\s+(\w+)', query)
    if m:
        return m.group(1)
    # Check for field-level detection
    for field in ("health", "serviceInfo", "echo", "submitTestData"):
        if field in query:
            return field
    return None


def _handle_graphql(query: str, variables: dict, operation_name: Optional[str]) -> dict:
    """Process a GraphQL request against the mock schema."""
    if not query:
        return {"errors": [{"message": "Query is required"}]}

    # Introspection
    if "__schema" in query or "__type" in query:
        return _handle_introspection(query)

    # Determine operation name
    op_name = operation_name or _parse_query_text(query)
    if not op_name:
        return {"errors": [{"message": "Could not determine operation. Provide operationName or use a named query."}]}

    result = _resolve_query(op_name, variables or {})
    if result is None:
        return {"errors": [{"message": f"Unknown operation: {op_name}"}]}

    return result


def _handle_introspection(query: str) -> dict:
    """Minimal introspection response for schema discovery."""
    types = [
        {
            "kind": "OBJECT", "name": "Query",
            "fields": [
                {"name": "health", "args": [], "type": {"kind": "NON_NULL", "name": None, "ofType": {"kind": "OBJECT", "name": "HealthStatus"}}},
                {"name": "serviceInfo", "args": [], "type": {"kind": "NON_NULL", "name": None, "ofType": {"kind": "OBJECT", "name": "ServiceInfo"}}},
                {"name": "echo", "args": [
                    {"name": "message", "type": {"kind": "NON_NULL", "name": None, "ofType": {"kind": "SCALAR", "name": "String"}}},
                    {"name": "messageInteger", "type": {"kind": "SCALAR", "name": "Int", "ofType": None}},
                    {"name": "messageDouble", "type": {"kind": "SCALAR", "name": "Float", "ofType": None}},
                    {"name": "messageUUID", "type": {"kind": "SCALAR", "name": "ID", "ofType": None}},
                    {"name": "messageTime", "type": {"kind": "SCALAR", "name": "String", "ofType": None}},
                ],
                 "type": {"kind": "NON_NULL", "name": None, "ofType": {"kind": "OBJECT", "name": "EchoResponse"}}},
            ],
        },
        {
            "kind": "OBJECT", "name": "Mutation",
            "fields": [
                {"name": "submitTestData", "args": [
                    {"name": "input", "type": {"kind": "NON_NULL", "name": None, "ofType": {"kind": "INPUT_OBJECT", "name": "TestDataInput"}}},
                ],
                 "type": {"kind": "NON_NULL", "name": None, "ofType": {"kind": "OBJECT", "name": "TestDataResponse"}}},
            ],
        },
    ]
    return {
        "data": {
            "__schema": {
                "queryType": {"name": "Query"},
                "mutationType": {"name": "Mutation"},
                "types": types,
            }
        }
    }


class GraphQLRequest(BaseModel):
    query: str = ""
    variables: Optional[dict] = None
    operationName: Optional[str] = None


class GraphQLHealthPlugin(PluginBase):
    @property
    def name(self) -> str:
        return "graphql-health"

    @property
    def description(self) -> str:
        return "Built-in mock GraphQL server for self-testing and demos"

    def _register_routes(self):
        @self.router.post("/graphql")
        async def handle_graphql(body: GraphQLRequest, request: Request):
            """Handle GraphQL requests against the built-in health schema."""
            result = _handle_graphql(body.query, body.variables or {}, body.operationName)
            return result

        @self.router.get("/schema")
        async def get_schema():
            """Return the GraphQL schema text for this endpoint."""
            return {"schema": HEALTH_SCHEMA}

        @self.router.get("/status")
        async def mock_status():
            """Quick health check for the mock GraphQL server."""
            return {
                "status": "ok",
                "request_count": _state["request_count"],
                "maintenance_mode": _state["maintenance_mode"],
                "uptime_seconds": int(time.time() - _state["start_time"]),
            }

        @self.router.post("/seed-config")
        async def seed_default_config(request: Request):
            """Create a default test configuration targeting the built-in health endpoint.

            This gives new users a ready-to-run demo config.
            Skips creation if a config named 'Self Load Test' already exists.
            """
            import uuid as _uuid

            from backend.plugins.auth_plugin import require_role
            from backend.plugins.storage_plugin import get_db

            user = require_role(request, "maintainer")
            db = get_db()
            now = datetime.now(timezone.utc).isoformat()

            # Check for existing seed config
            existing = db.execute(
                "SELECT id FROM test_configs WHERE name IN (?, ?)",
                ("Self Load Test", "Health Endpoint Demo"),
            ).fetchone()
            if existing:
                return {"id": existing["id"], "status": "exists", "message": "Default config already exists"}

            config_id = str(_uuid.uuid4())
            operations = [
                {
                    "name": "health",
                    "type": "query",
                    "query": "query health { health { status uptime_seconds request_count maintenance_mode timestamp } }",
                    "enabled": True,
                    "tps_percentage": 30,
                    "delay_start_sec": 0,
                    "data_range_start": 1,
                    "data_range_end": 100,
                    "variables": [],
                },
                {
                    "name": "serviceInfo",
                    "type": "query",
                    "query": "query serviceInfo { serviceInfo { name version environment features } }",
                    "enabled": True,
                    "tps_percentage": 20,
                    "delay_start_sec": 0,
                    "data_range_start": 1,
                    "data_range_end": 100,
                    "variables": [],
                },
                {
                    "name": "echo",
                    "type": "query",
                    "query": "query echo($message: String!, $messageInteger: Int, $messageDouble: Float, $messageUUID: ID, $messageTime: String) { echo(message: $message, messageInteger: $messageInteger, messageDouble: $messageDouble, messageUUID: $messageUUID, messageTime: $messageTime) { message messageInteger messageDouble messageUUID messageTime received_at request_number } }",
                    "enabled": True,
                    "tps_percentage": 25,
                    "delay_start_sec": 0,
                    "data_range_start": 1,
                    "data_range_end": 100,
                    "variables": [
                        {"name": "message", "type": "String!", "value": "test-{r}", "required": True},
                        {"name": "messageInteger", "type": "Int", "value": "{r}", "required": False},
                        {"name": "messageDouble", "type": "Float", "value": "{r}.5", "required": False},
                        {"name": "messageUUID", "type": "ID", "value": "uuid-{r}", "required": False},
                        {"name": "messageTime", "type": "String", "value": "2026-01-01T00:{r}:00Z", "required": False},
                    ],
                },
                {
                    "name": "submitTestData",
                    "type": "mutation",
                    "query": "mutation submitTestData($input: TestDataInput!) { submitTestData(input: $input) { id label count score referenceId scheduledAt active processed_at } }",
                    "enabled": True,
                    "tps_percentage": 25,
                    "delay_start_sec": 0,
                    "data_range_start": 1,
                    "data_range_end": 100,
                    "variables": [
                        {"name": "input", "type": "TestDataInput!", "value": {"label": "item-{r}", "count": "{r}", "score": "{r}.99", "referenceId": "ref-{r}", "scheduledAt": "2026-01-01T{r}:00:00Z", "active": True}, "required": True},
                    ],
                },
            ]

            config_json = json.dumps({
                "global_params": {
                    "name": "Self Load Test",
                    "description": "Built-in load test targeting the GraphQL health endpoint (self-test)",
                    "host": "http://localhost:8899",
                    "graphql_path": "/api/graphql-health/graphql",
                    "user_count": 5,
                    "ramp_up_sec": 5,
                    "duration_sec": 30,
                },
                "operations": operations,
                "engine": "locust",
                "debug_mode": False,
                "cleanup_on_stop": False,
                "auth_provider_id": "",
            })

            db.execute(
                "INSERT INTO test_configs (id, name, description, schema_text, config_json, created_by, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (config_id, "Self Load Test", "Built-in load test targeting the GraphQL health endpoint (self-test)",
                 HEALTH_SCHEMA, config_json, user["username"], now, now),
            )
            db.commit()
            return {"id": config_id, "status": "created", "message": "Default config created successfully"}
