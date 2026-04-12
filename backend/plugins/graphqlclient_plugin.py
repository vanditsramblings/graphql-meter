"""GraphQL Client plugin — execute queries against target environments.

Provides a built-in GraphQL client for:
- Verifying requests/responses before load testing
- Running ad-hoc queries against any configured environment
- Importing operations from saved test configs
- Saving and managing reusable GraphQL requests
"""

import json
import uuid
import time
import base64
import tempfile
import os
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import HTTPException, Request
from pydantic import BaseModel

from backend.core.plugin_base import PluginBase
from backend.plugins.storage_plugin import get_db
from backend.plugins.auth_plugin import require_auth, require_role


# ---------- Request models ----------

class GraphQLExecuteRequest(BaseModel):
    """Execute a GraphQL query against a target."""
    query: str
    variables: dict = {}
    operation_name: str = ""
    environment_id: str = ""
    auth_provider_id: str = ""
    # Direct target (if no environment selected)
    target_url: str = ""
    headers: dict = {}
    verify_ssl: bool = True
    timeout_sec: int = 30


class GraphQLRequestSaveRequest(BaseModel):
    """Save a reusable GraphQL request."""
    id: Optional[str] = None
    name: str
    description: str = ""
    folder_name: str = ""
    environment_id: str = ""
    auth_provider_id: str = ""
    query: str = ""
    variables_json: str = "{}"
    headers_json: str = "{}"
    config_id: str = ""
    operation_name: str = ""


class IntrospectionRequest(BaseModel):
    """Run introspection against a target."""
    environment_id: str = ""
    target_url: str = ""
    auth_provider_id: str = ""
    headers: dict = {}
    verify_ssl: bool = True


# ---------- Introspection query ----------

INTROSPECTION_QUERY = """
query IntrospectionQuery {
  __schema {
    queryType { name }
    mutationType { name }
    subscriptionType { name }
    types {
      kind
      name
      description
      fields(includeDeprecated: true) {
        name
        description
        args {
          name
          description
          type { ...TypeRef }
          defaultValue
        }
        type { ...TypeRef }
        isDeprecated
        deprecationReason
      }
      inputFields {
        name
        description
        type { ...TypeRef }
        defaultValue
      }
      interfaces { ...TypeRef }
      enumValues(includeDeprecated: true) {
        name
        description
        isDeprecated
        deprecationReason
      }
      possibleTypes { ...TypeRef }
    }
    directives {
      name
      description
      locations
      args {
        name
        description
        type { ...TypeRef }
        defaultValue
      }
    }
  }
}

fragment TypeRef on __Type {
  kind
  name
  ofType {
    kind
    name
    ofType {
      kind
      name
      ofType {
        kind
        name
        ofType {
          kind
          name
          ofType {
            kind
            name
            ofType {
              kind
              name
            }
          }
        }
      }
    }
  }
}
"""


def _resolve_target(env_id: str = "", target_url: str = "", auth_provider_id: str = "",
                     extra_headers: Optional[dict] = None, verify_ssl: bool = True) -> dict:
    """Resolve environment or direct URL to connection params."""
    result = {
        "url": target_url,
        "headers": {"Content-Type": "application/json"},
        "verify_ssl": verify_ssl,
        "cert": None,
        "cert_password": None,
    }

    if extra_headers:
        result["headers"].update(extra_headers)

    if env_id:
        db = get_db()
        row = db.execute("SELECT * FROM environments WHERE id = ?", (env_id,)).fetchone()
        if row:
            env = dict(row)
            base = env.get("base_url", "").rstrip("/")
            path = env.get("graphql_path", "/graphql")
            result["url"] = f"{base}{path}"
            result["verify_ssl"] = bool(env.get("verify_ssl", 1))

            # Parse environment headers
            try:
                env_headers = json.loads(env.get("headers_json", "{}"))
                result["headers"].update(env_headers)
            except Exception:
                pass

            # Use environment's auth provider if not overridden
            if not auth_provider_id and env.get("auth_provider_id"):
                auth_provider_id = env["auth_provider_id"]

            # Handle TLS certificates
            cert_data = env.get("cert_data", "")
            key_data = env.get("key_data", "")
            if cert_data and key_data:
                result["cert"] = (cert_data, key_data)

    # Resolve auth headers
    if auth_provider_id:
        try:
            from backend.plugins.authproviders_plugin import get_cached_auth_header
            auth_headers = get_cached_auth_header(auth_provider_id)
            if auth_headers:
                result["headers"].update(auth_headers)
        except Exception:
            pass

    return result


def _write_temp_cert_files(cert_data: str, key_data: str) -> tuple:
    """Write base64-encoded cert/key to temp files for httpx. Returns (cert_path, key_path)."""
    cert_path = key_path = None
    try:
        if cert_data:
            cert_bytes = base64.b64decode(cert_data)
            f = tempfile.NamedTemporaryFile(delete=False, suffix=".pem")
            f.write(cert_bytes)
            f.close()
            cert_path = f.name
        if key_data:
            key_bytes = base64.b64decode(key_data)
            f = tempfile.NamedTemporaryFile(delete=False, suffix=".key")
            f.write(key_bytes)
            f.close()
            key_path = f.name
    except Exception:
        pass
    return cert_path, key_path


def _cleanup_temp_files(*paths):
    """Remove temporary certificate files."""
    for p in paths:
        if p:
            try:
                os.unlink(p)
            except Exception:
                pass


class GraphQLClientPlugin(PluginBase):
    @property
    def name(self) -> str:
        return "graphqlclient"

    @property
    def description(self) -> str:
        return "Built-in GraphQL client for query execution and verification"

    def _register_routes(self):

        @self.router.post("/execute")
        async def execute_query(body: GraphQLExecuteRequest, request: Request):
            """Execute a GraphQL query and return the response."""
            require_auth(request)

            if not body.query.strip():
                raise HTTPException(400, "Query is required")

            target = _resolve_target(
                env_id=body.environment_id,
                target_url=body.target_url,
                auth_provider_id=body.auth_provider_id,
                extra_headers=body.headers,
                verify_ssl=body.verify_ssl,
            )

            if not target["url"]:
                raise HTTPException(400, "No target URL specified. Select an environment or provide a direct URL.")

            # Build GraphQL payload
            payload = {"query": body.query , "variables": {}, "operationName": ""}
            if body.variables:
                payload["variables"] = body.variables
            if body.operation_name:
                payload["operationName"] = body.operation_name

            # Handle mTLS certificates
            cert_path = key_path = None
            cert_info = target.get("cert")
            if cert_info and isinstance(cert_info, tuple):
                cert_path, key_path = _write_temp_cert_files(cert_info[0], cert_info[1])

            start_time = time.time()
            try:
                client_kwargs = {
                    "timeout": body.timeout_sec,
                    "verify": target["verify_ssl"],
                }
                if cert_path and key_path:
                    client_kwargs["cert"] = (cert_path, key_path)

                async with httpx.AsyncClient(**client_kwargs) as client:
                    resp = await client.post(
                        target["url"],
                        json=payload,
                        headers=target["headers"],
                    )

                elapsed_ms = (time.time() - start_time) * 1000

                # Parse response
                try:
                    response_data = resp.json()
                except Exception:
                    response_data = {"raw": resp.text[:5000]}

                has_errors = "errors" in response_data if isinstance(response_data, dict) else False

                return {
                    "success": resp.status_code == 200 and not has_errors,
                    "status_code": resp.status_code,
                    "elapsed_ms": round(elapsed_ms, 2),
                    "response": response_data,
                    "response_headers": dict(resp.headers),
                    "has_errors": has_errors,
                    "target_url": target["url"],
                }

            except httpx.ConnectError as e:
                return {
                    "success": False,
                    "status_code": 0,
                    "elapsed_ms": round((time.time() - start_time) * 1000, 2),
                    "error": f"Connection failed: {str(e)}",
                    "target_url": target["url"],
                }
            except httpx.TimeoutException:
                return {
                    "success": False,
                    "status_code": 0,
                    "elapsed_ms": round((time.time() - start_time) * 1000, 2),
                    "error": f"Request timed out after {body.timeout_sec}s",
                    "target_url": target["url"],
                }
            except Exception as e:
                return {
                    "success": False,
                    "status_code": 0,
                    "elapsed_ms": round((time.time() - start_time) * 1000, 2),
                    "error": str(e),
                    "target_url": target["url"],
                }
            finally:
                _cleanup_temp_files(cert_path, key_path)

        @self.router.post("/introspect")
        async def introspect(body: IntrospectionRequest, request: Request):
            """Run introspection query against a GraphQL endpoint."""
            require_auth(request)

            target = _resolve_target(
                env_id=body.environment_id,
                target_url=body.target_url,
                auth_provider_id=body.auth_provider_id,
                extra_headers=body.headers,
                verify_ssl=body.verify_ssl,
            )

            if not target["url"]:
                raise HTTPException(400, "No target URL specified")

            payload = {"query": INTROSPECTION_QUERY}

            try:
                async with httpx.AsyncClient(
                    timeout=30, verify=target["verify_ssl"]
                ) as client:
                    resp = await client.post(
                        target["url"],
                        json=payload,
                        headers=target["headers"],
                    )

                if resp.status_code != 200:
                    return {"success": False, "error": f"HTTP {resp.status_code}: {resp.text[:500]}"}

                data = resp.json()
                if "errors" in data:
                    return {"success": False, "error": "Introspection errors", "details": data["errors"]}

                schema = data.get("data", {}).get("__schema", {})

                # Extract operations summary
                types = schema.get("types", [])
                query_type = schema.get("queryType", {}).get("name", "Query")
                mutation_type = (schema.get("mutationType") or {}).get("name", "Mutation")

                operations = []
                for t in types:
                    if t["name"] == query_type and t.get("fields"):
                        for f in t["fields"]:
                            operations.append({
                                "name": f["name"],
                                "type": "query",
                                "description": f.get("description", ""),
                                "args": [{"name": a["name"], "type": _format_type_ref(a["type"])} for a in (f.get("args") or [])],
                            })
                    elif t["name"] == mutation_type and t.get("fields"):
                        for f in t["fields"]:
                            operations.append({
                                "name": f["name"],
                                "type": "mutation",
                                "description": f.get("description", ""),
                                "args": [{"name": a["name"], "type": _format_type_ref(a["type"])} for a in (f.get("args") or [])],
                            })

                return {
                    "success": True,
                    "schema": schema,
                    "operations": operations,
                    "query_count": len([o for o in operations if o["type"] == "query"]),
                    "mutation_count": len([o for o in operations if o["type"] == "mutation"]),
                }

            except Exception as e:
                return {"success": False, "error": str(e)}

        # ---------- Saved requests CRUD ----------

        @self.router.get("/requests/list")
        async def list_requests(request: Request):
            """List saved GraphQL requests and explicit folders."""
            require_auth(request)
            db = get_db()
            rows = db.execute(
                "SELECT id, name, description, folder_name, environment_id, auth_provider_id, "
                "config_id, operation_name, query, created_by, created_at, updated_at "
                "FROM graphql_requests ORDER BY folder_name, updated_at DESC"
            ).fetchall()
            folders = db.execute("SELECT id, path, created_at FROM graphql_folders ORDER BY path").fetchall()
            return {
                "requests": [dict(r) for r in rows],
                "folders": [dict(f) for f in folders],
            }

        @self.router.get("/requests/{request_id}")
        async def get_request(request_id: str, request: Request):
            """Get a saved GraphQL request with full details."""
            require_auth(request)
            db = get_db()
            row = db.execute("SELECT * FROM graphql_requests WHERE id = ?", (request_id,)).fetchone()
            if not row:
                raise HTTPException(404, "Request not found")
            result = dict(row)
            # Parse JSON fields
            for field in ("variables_json", "headers_json"):
                try:
                    result[field] = json.loads(result.get(field, "{}"))
                except Exception:
                    result[field] = {}
            try:
                result["last_response_json"] = json.loads(result.get("last_response_json", "{}"))
            except Exception:
                result["last_response_json"] = {}
            return result

        @self.router.post("/requests/save")
        async def save_request(body: GraphQLRequestSaveRequest, request: Request):
            """Save a GraphQL request."""
            user = require_role(request, "maintainer")
            db = get_db()
            now = datetime.now(timezone.utc).isoformat()

            if not body.name.strip():
                raise HTTPException(400, "Name is required")

            # Validate JSON fields
            for field_name, field_val in [("variables_json", body.variables_json), ("headers_json", body.headers_json)]:
                try:
                    json.loads(field_val)
                except json.JSONDecodeError:
                    raise HTTPException(400, f"Invalid JSON in {field_name}")

            if body.id:
                existing = db.execute("SELECT id FROM graphql_requests WHERE id = ?", (body.id,)).fetchone()
                if existing:
                    db.execute(
                        """UPDATE graphql_requests SET name=?, description=?, folder_name=?, environment_id=?,
                        auth_provider_id=?, query=?, variables_json=?, headers_json=?,
                        config_id=?, operation_name=?, updated_at=?
                        WHERE id=?""",
                        (body.name, body.description, body.folder_name, body.environment_id,
                         body.auth_provider_id, body.query, body.variables_json,
                         body.headers_json, body.config_id, body.operation_name,
                         now, body.id),
                    )
                    db.commit()
                    return {"id": body.id, "status": "updated"}

            req_id = str(uuid.uuid4())
            db.execute(
                """INSERT INTO graphql_requests (id, name, description, folder_name, environment_id,
                auth_provider_id, query, variables_json, headers_json,
                config_id, operation_name, created_by, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (req_id, body.name, body.description, body.folder_name, body.environment_id,
                 body.auth_provider_id, body.query, body.variables_json,
                 body.headers_json, body.config_id, body.operation_name,
                 user["username"], now, now),
            )
            db.commit()
            return {"id": req_id, "status": "created"}

        @self.router.delete("/requests/{request_id}")
        async def delete_request(request_id: str, request: Request):
            """Delete a saved GraphQL request."""
            require_role(request, "maintainer")
            db = get_db()
            row = db.execute("SELECT id FROM graphql_requests WHERE id = ?", (request_id,)).fetchone()
            if not row:
                raise HTTPException(404, "Request not found")
            db.execute("DELETE FROM graphql_requests WHERE id = ?", (request_id,))
            db.commit()
            return {"status": "deleted"}

        @self.router.post("/requests/{request_id}/execute")
        async def execute_saved_request(request_id: str, request: Request):
            """Execute a previously saved request."""
            require_auth(request)
            db = get_db()
            row = db.execute("SELECT * FROM graphql_requests WHERE id = ?", (request_id,)).fetchone()
            if not row:
                raise HTTPException(404, "Request not found")

            saved = dict(row)
            variables = {}
            try:
                variables = json.loads(saved.get("variables_json", "{}"))
            except Exception:
                pass
            headers = {}
            try:
                headers = json.loads(saved.get("headers_json", "{}"))
            except Exception:
                pass

            # Build execute request
            exec_req = GraphQLExecuteRequest(
                query=saved.get("query", ""),
                variables=variables,
                operation_name=saved.get("operation_name", ""),
                environment_id=saved.get("environment_id", ""),
                auth_provider_id=saved.get("auth_provider_id", ""),
                headers=headers,
            )
            result = await execute_query(exec_req, request)

            # Save last response
            try:
                response_json = json.dumps(result)
                now = datetime.now(timezone.utc).isoformat()
                db.execute(
                    "UPDATE graphql_requests SET last_response_json=?, updated_at=? WHERE id=?",
                    (response_json, now, request_id),
                )
                db.commit()
            except Exception:
                pass

            return result

        @self.router.get("/from-config/{config_id}")
        async def get_operations_from_config(config_id: str, request: Request):
            """Import operations from a saved test config for use in GraphQL client."""
            require_auth(request)
            db = get_db()
            row = db.execute("SELECT config_json, schema_text, name FROM test_configs WHERE id = ?", (config_id,)).fetchone()
            if not row:
                raise HTTPException(404, "Test config not found")

            config_data = {}
            try:
                config_data = json.loads(row["config_json"]) if row["config_json"] else {}
            except Exception:
                pass

            operations = config_data.get("operations", [])
            global_params = config_data.get("global_params", {})

            result_ops = []
            for op in operations:
                result_ops.append({
                    "name": op.get("name", ""),
                    "type": op.get("type", "query"),
                    "query": op.get("query", ""),
                    "variables": {v.get("name", ""): v.get("value", "") for v in op.get("variables", [])},
                    "enabled": op.get("enabled", True),
                })

            return {
                "config_name": row["name"],
                "config_id": config_id,
                "operations": result_ops,
                "global_params": global_params,
                "schema_text": row["schema_text"] or "",
            }

        @self.router.post("/preview")
        async def preview_request(body: GraphQLExecuteRequest, request: Request):
            """Preview the final request that would be sent (headers, URL, payload)."""
            require_auth(request)

            target = _resolve_target(
                env_id=body.environment_id,
                target_url=body.target_url,
                auth_provider_id=body.auth_provider_id,
                extra_headers=body.headers,
                verify_ssl=body.verify_ssl,
            )

            payload = {"query": body.query, "variables": body.variables or {}}
            if body.operation_name:
                payload["operationName"] = body.operation_name

            # Redact auth tokens for display
            display_headers = dict(target["headers"])

            return {
                "url": target["url"],
                "method": "POST",
                "headers": display_headers,
                "body": payload,
                "verify_ssl": target["verify_ssl"],
                "has_cert": target.get("cert") is not None,
            }

        @self.router.post("/export/curl")
        async def export_curl(body: GraphQLExecuteRequest, request: Request):
            """Export the request as a cURL command."""
            require_auth(request)

            target = _resolve_target(
                env_id=body.environment_id,
                target_url=body.target_url,
                auth_provider_id=body.auth_provider_id,
                extra_headers=body.headers,
                verify_ssl=body.verify_ssl,
            )

            if not target["url"]:
                raise HTTPException(400, "No target URL specified")

            payload = {"query": body.query, "variables": body.variables or {}}
            if body.operation_name:
                payload["operationName"] = body.operation_name

            # Build curl command
            parts = ["curl -X POST"]
            if not target["verify_ssl"]:
                parts.append("  --insecure")
            parts.append(f"  '{target['url']}'")
            for k, v in target["headers"].items():
                # Redact Authorization value for security
                display_v = "***REDACTED***" if k.lower() == "authorization" else v
                parts.append(f"  -H '{k}: {display_v}'")
            payload_str = json.dumps(payload, separators=(',', ':'))
            parts.append(f"  -d '{payload_str}'")

            return {"format": "curl", "content": " \\\n".join(parts)}

        @self.router.post("/export/postman")
        async def export_postman(body: GraphQLExecuteRequest, request: Request):
            """Export the request as a Postman collection JSON."""
            require_auth(request)

            target = _resolve_target(
                env_id=body.environment_id,
                target_url=body.target_url,
                auth_provider_id=body.auth_provider_id,
                extra_headers=body.headers,
                verify_ssl=body.verify_ssl,
            )

            if not target["url"]:
                raise HTTPException(400, "No target URL specified")

            payload = {"query": body.query, "variables": body.variables or {}}
            if body.operation_name:
                payload["operationName"] = body.operation_name

            # Build Postman collection v2.1
            header_list = []
            for k, v in target["headers"].items():
                header_list.append({"key": k, "value": v})

            collection = {
                "info": {
                    "name": body.operation_name or "GraphQL Request",
                    "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
                },
                "item": [{
                    "name": body.operation_name or "GraphQL Query",
                    "request": {
                        "method": "POST",
                        "header": header_list,
                        "body": {
                            "mode": "graphql",
                            "graphql": {
                                "query": body.query,
                                "variables": json.dumps(body.variables or {}),
                            },
                        },
                        "url": {"raw": target["url"], "protocol": target["url"].split("://")[0] if "://" in target["url"] else "https"},
                    },
                }],
            }

            return {"format": "postman", "content": json.dumps(collection, indent=2)}

        @self.router.post("/folders/create")
        async def create_folder(request: Request, body: dict):
            """Create an explicit folder (supports nested paths like 'Auth/OAuth2')."""
            user = require_role(request, "maintainer")
            folder_path = body.get("path", "").strip().strip("/")
            if not folder_path:
                raise HTTPException(400, "path is required")
            db = get_db()
            now = datetime.now(timezone.utc).isoformat()
            # Ensure all ancestor folders exist
            parts = folder_path.split("/")
            for i in range(1, len(parts) + 1):
                ancestor = "/".join(parts[:i])
                existing = db.execute("SELECT id FROM graphql_folders WHERE path = ?", (ancestor,)).fetchone()
                if not existing:
                    db.execute(
                        "INSERT INTO graphql_folders (id, path, created_by, created_at) VALUES (?,?,?,?)",
                        (str(uuid.uuid4()), ancestor, user["username"], now),
                    )
            db.commit()
            return {"status": "created", "path": folder_path}

        @self.router.post("/folders/rename")
        async def rename_folder(request: Request, body: dict):
            """Rename a folder (updates all requests and sub-folders with matching prefix)."""
            require_role(request, "maintainer")
            old_name = body.get("old_name", "").strip().strip("/")
            new_name = body.get("new_name", "").strip().strip("/")
            if not old_name or not new_name:
                raise HTTPException(400, "Both old_name and new_name are required")
            db = get_db()
            # Rename exact match and children for requests
            db.execute(
                "UPDATE graphql_requests SET folder_name = ? WHERE folder_name = ?",
                (new_name, old_name),
            )
            # Rename children: old_name/child -> new_name/child
            prefix = old_name + "/"
            rows = db.execute(
                "SELECT id, folder_name FROM graphql_requests WHERE folder_name LIKE ?",
                (prefix + "%",),
            ).fetchall()
            for r in rows:
                new_folder = new_name + "/" + r["folder_name"][len(prefix):]
                db.execute("UPDATE graphql_requests SET folder_name = ? WHERE id = ?", (new_folder, r["id"]))

            # Rename the folder record and children
            db.execute("UPDATE graphql_folders SET path = ? WHERE path = ?", (new_name, old_name))
            folder_rows = db.execute("SELECT id, path FROM graphql_folders WHERE path LIKE ?", (prefix + "%",)).fetchall()
            for f in folder_rows:
                new_path = new_name + "/" + f["path"][len(prefix):]
                db.execute("UPDATE graphql_folders SET path = ? WHERE id = ?", (new_path, f["id"]))

            db.commit()
            return {"status": "renamed", "old_name": old_name, "new_name": new_name}

        @self.router.post("/folders/delete")
        async def delete_folder(request: Request, body: dict):
            """Delete a folder, its sub-folders, and all contained requests."""
            require_role(request, "maintainer")
            folder_name = body.get("folder_name", "").strip().strip("/")
            if not folder_name:
                raise HTTPException(400, "folder_name is required")
            db = get_db()
            prefix = folder_name + "/"
            # Delete requests in this folder and sub-folders
            db.execute("DELETE FROM graphql_requests WHERE folder_name = ?", (folder_name,))
            db.execute("DELETE FROM graphql_requests WHERE folder_name LIKE ?", (prefix + "%",))
            # Delete folder records
            db.execute("DELETE FROM graphql_folders WHERE path = ?", (folder_name,))
            db.execute("DELETE FROM graphql_folders WHERE path LIKE ?", (prefix + "%",))
            db.commit()
            return {"status": "deleted", "folder_name": folder_name}


def _format_type_ref(type_ref: dict) -> str:
    """Format a GraphQL type reference into a readable string."""
    if not type_ref:
        return "Unknown"
    kind = type_ref.get("kind", "")
    name = type_ref.get("name", "")
    of_type = type_ref.get("ofType")

    if kind == "NON_NULL":
        return f"{_format_type_ref(of_type or {})}!"
    elif kind == "LIST":
        return f"[{_format_type_ref(of_type or {})}]"
    elif name:
        return name
    return "Unknown"
