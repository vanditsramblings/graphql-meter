"""GraphQL Health endpoint — a built-in mock GraphQL server for testing.

Provides a simple schema with:
  - Query: health, serviceInfo, echo
  - Mutation: setMaintenanceMode, resetStats

This serves as:
  1. A self-diagnostic endpoint (the app can test itself)
  2. A default target for new users to experiment with load testing
  3. A validation target for debug mode and engine testing
"""

import json
import time
import os
from datetime import datetime, timezone

from fastapi import Request
from pydantic import BaseModel
from typing import Optional

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
  echo(message: String!): EchoResponse!
}

type Mutation {
  setMaintenanceMode(enabled: Boolean!): MaintenanceResult!
  resetStats: ResetResult!
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
  received_at: String!
  request_number: Int!
}

type MaintenanceResult {
  success: Boolean!
  maintenance_mode: Boolean!
  message: String!
}

type ResetResult {
  success: Boolean!
  previous_count: Int!
  message: String!
}
'''


def _resolve_query(operation_name: str, variables: dict) -> dict:
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
                    "version": "0.1.0",
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
                    "received_at": now,
                    "request_number": _state["request_count"],
                }
            }
        }

    if operation_name in ("setMaintenanceMode", "SetMaintenanceMode"):
        enabled = variables.get("enabled", False)
        _state["maintenance_mode"] = bool(enabled)
        return {
            "data": {
                "setMaintenanceMode": {
                    "success": True,
                    "maintenance_mode": _state["maintenance_mode"],
                    "message": f"Maintenance mode {'enabled' if enabled else 'disabled'}",
                }
            }
        }

    if operation_name in ("resetStats", "ResetStats"):
        prev = _state["request_count"]
        _state["request_count"] = 0
        return {
            "data": {
                "resetStats": {
                    "success": True,
                    "previous_count": prev,
                    "message": "Stats reset successfully",
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
    for field in ("health", "serviceInfo", "echo", "setMaintenanceMode", "resetStats"):
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
                {"name": "echo", "args": [{"name": "message", "type": {"kind": "NON_NULL", "name": None, "ofType": {"kind": "SCALAR", "name": "String"}}}],
                 "type": {"kind": "NON_NULL", "name": None, "ofType": {"kind": "OBJECT", "name": "EchoResponse"}}},
            ],
        },
        {
            "kind": "OBJECT", "name": "Mutation",
            "fields": [
                {"name": "setMaintenanceMode", "args": [{"name": "enabled", "type": {"kind": "NON_NULL", "name": None, "ofType": {"kind": "SCALAR", "name": "Boolean"}}}],
                 "type": {"kind": "NON_NULL", "name": None, "ofType": {"kind": "OBJECT", "name": "MaintenanceResult"}}},
                {"name": "resetStats", "args": [],
                 "type": {"kind": "NON_NULL", "name": None, "ofType": {"kind": "OBJECT", "name": "ResetResult"}}},
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
