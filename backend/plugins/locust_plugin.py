"""Locust plugin — start/stop/status for Locust test runs."""

from fastapi import HTTPException, Request
from pydantic import BaseModel
from typing import Optional

from backend.core.plugin_base import PluginBase
from backend.plugins.auth_plugin import require_auth, require_role
from backend.locust_engine import engine as locust_engine


class StartRunRequest(BaseModel):
    config_id: Optional[str] = None
    name: str = ""
    global_params: dict = {}
    operations: list = []
    schema_text: str = ""
    engine: str = "locust"
    debug_mode: bool = False
    cleanup_on_stop: bool = False
    auth_provider_id: Optional[str] = None


class LocustPlugin(PluginBase):
    @property
    def name(self) -> str:
        return "locust"

    @property
    def description(self) -> str:
        return "Start/stop/status for Locust load test runs"

    def _register_routes(self):
        @self.router.post("/start")
        async def start_run(body: StartRunRequest, request: Request):
            user = require_auth(request)
            try:
                config = {
                    "config_id": body.config_id,
                    "name": body.name,
                    "global_params": body.global_params,
                    "operations": body.operations,
                    "debug_mode": body.debug_mode,
                    "cleanup_on_stop": body.cleanup_on_stop,
                    "auth_provider_id": body.auth_provider_id,
                }
                result = locust_engine.start_run(config, user["username"])
                return result
            except RuntimeError as e:
                raise HTTPException(429, str(e))
            except Exception as e:
                raise HTTPException(500, f"Failed to start run: {e}")

        @self.router.post("/stop/{run_id}")
        async def stop_run(run_id: str, request: Request):
            require_auth(request)
            return locust_engine.stop_run(run_id)

        @self.router.get("/status/{run_id}")
        async def run_status(run_id: str, request: Request):
            require_auth(request)
            return locust_engine.get_status(run_id)

        @self.router.get("/runs")
        async def list_runs(request: Request):
            require_auth(request)
            from backend.plugins.storage_plugin import get_db
            db = get_db()
            rows = db.execute(
                "SELECT id, config_id, name, status, started_at, completed_at, user_count, duration_sec, host "
                "FROM test_runs WHERE engine = 'locust' ORDER BY started_at DESC LIMIT 50"
            ).fetchall()
            return {"runs": [dict(r) for r in rows]}
