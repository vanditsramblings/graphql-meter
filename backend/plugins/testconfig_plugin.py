"""Test config plugin — CRUD for test definitions, TPS% validation."""

import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, Request
from pydantic import BaseModel

from backend.core.plugin_base import PluginBase
from backend.plugins.auth_plugin import require_auth, require_role
from backend.plugins.storage_plugin import get_db


class TestConfigSaveRequest(BaseModel):
    id: Optional[str] = None
    name: str
    description: str = ""
    schema_text: str = ""
    config_json: dict = {}


class TestConfigPlugin(PluginBase):
    @property
    def name(self) -> str:
        return "testconfig"

    @property
    def description(self) -> str:
        return "CRUD test configurations, TPS% validation"

    def _register_routes(self):
        @self.router.get("/list")
        async def list_configs(request: Request):
            require_auth(request)
            db = get_db()
            rows = db.execute(
                "SELECT id, name, description, created_by, created_at, updated_at FROM test_configs ORDER BY updated_at DESC"
            ).fetchall()
            return {"configs": [dict(r) for r in rows]}

        @self.router.get("/{config_id}")
        async def get_config(config_id: str, request: Request):
            require_auth(request)
            db = get_db()
            row = db.execute("SELECT * FROM test_configs WHERE id = ?", (config_id,)).fetchone()
            if not row:
                raise HTTPException(404, "Config not found")
            result = dict(row)
            if result.get("config_json"):
                try:
                    result["config_json"] = json.loads(result["config_json"])
                except Exception:
                    pass
            return result

        @self.router.post("/save")
        async def save_config(body: TestConfigSaveRequest, request: Request):
            user = require_role(request, "maintainer")
            db = get_db()
            now = datetime.now(timezone.utc).isoformat()

            # Validate TPS percentages
            operations = body.config_json.get("operations", [])
            enabled_ops = [o for o in operations if o.get("enabled", True)]
            if enabled_ops:
                total_tps = sum(o.get("tps_percentage", 0) for o in enabled_ops)
                if abs(total_tps - 100) > 0.1:
                    raise HTTPException(400, f"Enabled operations TPS% must sum to 100 (got {total_tps:.1f})")

            config_json_str = json.dumps(body.config_json)

            if body.id:
                existing = db.execute("SELECT id FROM test_configs WHERE id = ?", (body.id,)).fetchone()
                if existing:
                    db.execute(
                        "UPDATE test_configs SET name=?, description=?, schema_text=?, config_json=?, updated_at=? WHERE id=?",
                        (body.name, body.description, body.schema_text, config_json_str, now, body.id),
                    )
                    db.commit()
                    return {"id": body.id, "status": "updated"}

            config_id = str(uuid.uuid4())
            db.execute(
                "INSERT INTO test_configs (id, name, description, schema_text, config_json, created_by, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (config_id, body.name, body.description, body.schema_text, config_json_str, user["username"], now, now),
            )
            db.commit()
            return {"id": config_id, "status": "created"}

        @self.router.delete("/{config_id}")
        async def delete_config(config_id: str, request: Request):
            require_role(request, "maintainer")
            db = get_db()
            row = db.execute("SELECT id FROM test_configs WHERE id = ?", (config_id,)).fetchone()
            if not row:
                raise HTTPException(404, "Config not found")
            # Detach runs from this config so FK constraint doesn't block deletion
            db.execute("UPDATE test_runs SET config_id = NULL WHERE config_id = ?", (config_id,))
            db.execute("DELETE FROM test_configs WHERE id = ?", (config_id,))
            db.commit()
            return {"status": "deleted"}

        @self.router.post("/validate")
        async def validate_config(body: TestConfigSaveRequest, request: Request):
            require_auth(request)
            errors = []
            if not body.name.strip():
                errors.append("Name is required")

            operations = body.config_json.get("operations", [])
            enabled_ops = [o for o in operations if o.get("enabled", True)]
            if not enabled_ops:
                errors.append("At least one operation must be enabled")
            else:
                total_tps = sum(o.get("tps_percentage", 0) for o in enabled_ops)
                if abs(total_tps - 100) > 0.1:
                    errors.append(f"TPS% must sum to 100 (got {total_tps:.1f})")

            gp = body.config_json.get("global_params", {})
            # Host is not required if an environment is selected
            if not gp.get("host") and not gp.get("environment_id"):
                errors.append("Host URL or Environment is required")

            return {"valid": len(errors) == 0, "errors": errors}

        @self.router.post("/duplicate/{config_id}")
        async def duplicate_config(config_id: str, request: Request):
            """Duplicate an existing test configuration."""
            user = require_role(request, "maintainer")
            db = get_db()
            row = db.execute("SELECT * FROM test_configs WHERE id = ?", (config_id,)).fetchone()
            if not row:
                raise HTTPException(404, "Config not found")

            src = dict(row)
            new_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc).isoformat()
            new_name = f"{src['name']} (Copy)"

            db.execute(
                "INSERT INTO test_configs (id, name, description, schema_text, config_json, created_by, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (new_id, new_name, src.get("description", ""), src.get("schema_text", ""),
                 src.get("config_json", "{}"), user["username"], now, now),
            )
            db.commit()
            return {"id": new_id, "status": "duplicated", "name": new_name}
