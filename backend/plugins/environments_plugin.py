"""Environments plugin — CRUD for named environment profiles."""

import json
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, Request
from pydantic import BaseModel
from typing import Optional

from backend.core.plugin_base import PluginBase
from backend.plugins.storage_plugin import get_db
from backend.plugins.auth_plugin import require_auth, require_role


class EnvironmentSaveRequest(BaseModel):
    id: Optional[str] = None
    name: str
    platform: str = "cloud"
    base_url: str = ""
    graphql_path: str = "/graphql"
    cert_path: str = ""
    key_path: str = ""
    notes: str = ""


class EnvironmentsPlugin(PluginBase):
    @property
    def name(self) -> str:
        return "environments"

    @property
    def description(self) -> str:
        return "Environment profiles CRUD"

    def __init__(self):
        super().__init__()
        self._seed_defaults()

    def _seed_defaults(self):
        try:
            db = get_db()
            count = db.execute("SELECT COUNT(*) as cnt FROM environments").fetchone()["cnt"]
            if count == 0:
                now = datetime.now(timezone.utc).isoformat()
                defaults = [
                    ("local", "cloud", "http://localhost:4000", "/graphql", "Local development"),
                    ("staging", "cloud", "https://staging.example.com", "/graphql", "Staging environment"),
                    ("production", "cloud", "https://api.example.com", "/graphql", "Production (read-only tests)"),
                ]
                for name, plat, url, path, notes in defaults:
                    db.execute(
                        "INSERT INTO environments (id,name,platform,base_url,graphql_path,notes,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
                        (str(uuid.uuid4()), name, plat, url, path, notes, now, now),
                    )
                db.commit()
        except Exception:
            pass

    def _register_routes(self):
        @self.router.get("/list")
        async def list_envs(request: Request):
            require_auth(request)
            db = get_db()
            rows = db.execute("SELECT * FROM environments ORDER BY name").fetchall()
            return {"environments": [dict(r) for r in rows]}

        @self.router.get("/{env_id}")
        async def get_env(env_id: str, request: Request):
            require_auth(request)
            db = get_db()
            row = db.execute("SELECT * FROM environments WHERE id = ?", (env_id,)).fetchone()
            if not row:
                raise HTTPException(404, "Environment not found")
            return dict(row)

        @self.router.post("/save")
        async def save_env(body: EnvironmentSaveRequest, request: Request):
            require_role(request, "maintainer")
            db = get_db()
            now = datetime.now(timezone.utc).isoformat()

            if body.id:
                existing = db.execute("SELECT id FROM environments WHERE id = ?", (body.id,)).fetchone()
                if existing:
                    db.execute(
                        "UPDATE environments SET name=?, platform=?, base_url=?, graphql_path=?, cert_path=?, key_path=?, notes=?, updated_at=? WHERE id=?",
                        (body.name, body.platform, body.base_url, body.graphql_path, body.cert_path, body.key_path, body.notes, now, body.id),
                    )
                    db.commit()
                    return {"id": body.id, "status": "updated"}

            env_id = str(uuid.uuid4())
            db.execute(
                "INSERT INTO environments (id,name,platform,base_url,graphql_path,cert_path,key_path,notes,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (env_id, body.name, body.platform, body.base_url, body.graphql_path, body.cert_path, body.key_path, body.notes, now, now),
            )
            db.commit()
            return {"id": env_id, "status": "created"}

        @self.router.delete("/{env_id}")
        async def delete_env(env_id: str, request: Request):
            require_role(request, "admin")
            db = get_db()
            row = db.execute("SELECT id FROM environments WHERE id = ?", (env_id,)).fetchone()
            if not row:
                raise HTTPException(404, "Environment not found")
            db.execute("DELETE FROM environments WHERE id = ?", (env_id,))
            db.commit()
            return {"status": "deleted"}
