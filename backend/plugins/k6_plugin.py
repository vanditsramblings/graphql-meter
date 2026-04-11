"""k6 plugin — start/stop/status for k6 test runs."""

from fastapi import HTTPException, Request
from pydantic import BaseModel
from typing import Optional

from backend.core.plugin_base import PluginBase
from backend.plugins.auth_plugin import require_auth, require_role
from backend.k6_engine import engine as k6_engine


class StartK6RunRequest(BaseModel):
    config_id: Optional[str] = None
    name: str = ""
    global_params: dict = {}
    operations: list = []
    schema_text: str = ""
    engine: str = "k6"
    debug_mode: bool = False
    cleanup_on_stop: bool = False
    auth_provider_id: Optional[str] = None


class K6Plugin(PluginBase):
    @property
    def name(self) -> str:
        return "k6"

    @property
    def description(self) -> str:
        return "Start/stop/status for k6 load test runs"

    def _register_routes(self):
        @self.router.post("/start")
        async def start_run(body: StartK6RunRequest, request: Request):
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
                result = k6_engine.start_run(config, user["username"])
                return result
            except RuntimeError as e:
                raise HTTPException(429, str(e))
            except Exception as e:
                raise HTTPException(500, f"Failed to start k6 run: {e}")

        @self.router.post("/stop/{run_id}")
        async def stop_run(run_id: str, request: Request):
            require_auth(request)
            return k6_engine.stop_run(run_id)

        @self.router.get("/status/{run_id}")
        async def run_status(run_id: str, request: Request):
            require_auth(request)
            raw = k6_engine.get_status(run_id)

            # Normalize engine response to frontend-expected format
            latest = raw.get("latest", {})
            ops_dict = latest.get("operations", {})
            ops_array = []
            for name, stats in ops_dict.items():
                ops_array.append({
                    "name": name,
                    "type": stats.get("operation_type", "query"),
                    "total_requests": stats.get("request_count", 0),
                    "failures": stats.get("failure_count", 0),
                    "rps": stats.get("tps_actual", 0),
                    "avg_response_time": stats.get("avg_response_ms", 0),
                    "p50": stats.get("p50_response_ms"),
                    "p90": stats.get("p90_response_ms"),
                    "p95": stats.get("p95_response_ms"),
                    "p99": stats.get("p99_response_ms"),
                    "avg_response_bytes": stats.get("avg_response_bytes", 0),
                    "avg_request_bytes": stats.get("avg_request_bytes", 0),
                    "total_response_bytes": stats.get("total_response_bytes", 0),
                    "total_request_bytes": stats.get("total_request_bytes", 0),
                })

            from backend.plugins.storage_plugin import get_db
            import json as _json
            db = get_db()
            run_row = db.execute(
                "SELECT name, started_at, config_snapshot, debug_mode, summary_json, status as db_status FROM test_runs WHERE id = ?",
                (raw.get("run_id", run_id),),
            ).fetchone()

            status = raw.get("status", "unknown")

            if status == "unknown" and run_row:
                status = run_row["db_status"] or "unknown"
                if not ops_array and run_row.get("summary_json"):
                    try:
                        summary = _json.loads(run_row["summary_json"]) if isinstance(run_row["summary_json"], str) else run_row["summary_json"]
                        for n, s in summary.get("operations", {}).items():
                            ops_array.append({
                                "name": n, "type": s.get("operation_type", "query"),
                                "total_requests": s.get("request_count", 0),
                                "failures": s.get("failure_count", 0),
                                "rps": s.get("tps_actual", 0),
                                "avg_response_time": s.get("avg_response_ms", 0),
                                "p50": s.get("p50_response_ms"), "p90": s.get("p90_response_ms"),
                                "p95": s.get("p95_response_ms"), "p99": s.get("p99_response_ms"),
                            })
                    except Exception:
                        pass
                if not ops_array:
                    op_rows = db.execute("SELECT * FROM operation_results WHERE run_id = ?", (run_id,)).fetchall()
                    for opr in op_rows:
                        ops_array.append({
                            "name": opr["operation_name"], "type": opr["operation_type"] or "query",
                            "total_requests": opr["request_count"] or 0, "failures": opr["failure_count"] or 0,
                            "rps": opr["tps_actual"] or 0, "avg_response_time": opr["avg_response_ms"] or 0,
                            "p50": opr["p50_response_ms"], "p90": opr["p90_response_ms"],
                            "p95": opr["p95_response_ms"], "p99": opr["p99_response_ms"],
                        })

            return {
                "run_id": raw.get("run_id", run_id),
                "status": status,
                "config_name": run_row["name"] if run_row else "",
                "started_at": run_row["started_at"] if run_row else None,
                "debug_mode": bool(run_row["debug_mode"]) if run_row else False,
                "user_count": latest.get("user_count", 0),
                "elapsed_sec": latest.get("elapsed_sec", 0),
                "operations": ops_array,
                "errors": raw.get("errors", []),
                "debug_logs": raw.get("debug_logs", []),
            }

        @self.router.get("/runs")
        async def list_runs(request: Request):
            require_auth(request)
            from backend.plugins.storage_plugin import get_db
            db = get_db()
            rows = db.execute(
                "SELECT id, config_id, name, status, started_at, completed_at, user_count, duration_sec, host "
                "FROM test_runs WHERE engine = 'k6' ORDER BY started_at DESC LIMIT 50"
            ).fetchall()
            return {"runs": [dict(r) for r in rows]}
