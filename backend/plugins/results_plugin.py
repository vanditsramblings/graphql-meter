"""Results plugin — run history, per-op stats, compare, trends, notes/tags."""

import json
from datetime import datetime, timezone

from fastapi import HTTPException, Request, Query
from pydantic import BaseModel
from typing import Optional

from backend.core.plugin_base import PluginBase
from backend.plugins.storage_plugin import get_db
from backend.plugins.auth_plugin import require_auth, require_role


class NotesRequest(BaseModel):
    notes: str = ""
    tags: str = ""


class ResultsPlugin(PluginBase):
    @property
    def name(self) -> str:
        return "results"

    @property
    def description(self) -> str:
        return "Run history, per-op stats, compare, trends, HTML export"

    def _register_routes(self):
        @self.router.get("/runs")
        async def list_runs(
            request: Request,
            status: Optional[str] = None,
            engine: Optional[str] = None,
            config_id: Optional[str] = None,
            limit: int = 50,
        ):
            require_auth(request)
            db = get_db()
            query = "SELECT id, config_id, name as config_name, status, engine, started_at, completed_at, user_count, duration_sec, host, created_by, notes, tags FROM test_runs WHERE 1=1"
            params = []
            if status:
                query += " AND status = ?"
                params.append(status)
            if engine:
                query += " AND engine = ?"
                params.append(engine)
            if config_id:
                query += " AND config_id = ?"
                params.append(config_id)
            query += " ORDER BY started_at DESC LIMIT ?"
            params.append(limit)
            rows = db.execute(query, params).fetchall()
            return {"runs": [dict(r) for r in rows]}

        @self.router.get("/runs/{run_id}")
        async def get_run(run_id: str, request: Request):
            require_auth(request)
            db = get_db()
            row = db.execute("SELECT * FROM test_runs WHERE id = ?", (run_id,)).fetchone()
            if not row:
                raise HTTPException(404, "Run not found")
            result = dict(row)
            for key in ("summary_json", "config_snapshot", "chart_snapshots"):
                if result.get(key):
                    try:
                        result[key] = json.loads(result[key])
                    except Exception:
                        pass
            return result

        @self.router.get("/runs/{run_id}/operations")
        async def get_run_operations(run_id: str, request: Request):
            require_auth(request)
            db = get_db()
            rows = db.execute(
                "SELECT * FROM operation_results WHERE run_id = ? ORDER BY operation_name",
                (run_id,),
            ).fetchall()
            return {"operations": [dict(r) for r in rows]}

        @self.router.get("/runs/{run_id}/errors")
        async def get_run_errors(run_id: str, request: Request):
            require_auth(request)
            db = get_db()
            row = db.execute("SELECT error_log FROM test_runs WHERE id = ?", (run_id,)).fetchone()
            if not row:
                raise HTTPException(404, "Run not found")
            return {"errors": row["error_log"] or ""}

        @self.router.put("/runs/{run_id}/notes")
        async def update_notes(run_id: str, body: NotesRequest, request: Request):
            require_role(request, "maintainer")
            db = get_db()
            db.execute(
                "UPDATE test_runs SET notes = ?, tags = ? WHERE id = ?",
                (body.notes, body.tags, run_id),
            )
            db.commit()
            return {"status": "updated"}

        @self.router.get("/compare")
        async def compare_runs(
            request: Request,
            run1: str = Query(...),
            run2: str = Query(...),
        ):
            require_auth(request)
            db = get_db()
            r1 = db.execute("SELECT * FROM test_runs WHERE id = ?", (run1,)).fetchone()
            r2 = db.execute("SELECT * FROM test_runs WHERE id = ?", (run2,)).fetchone()
            if not r1 or not r2:
                raise HTTPException(404, "One or both runs not found")

            ops1 = db.execute("SELECT * FROM operation_results WHERE run_id = ?", (run1,)).fetchall()
            ops2 = db.execute("SELECT * FROM operation_results WHERE run_id = ?", (run2,)).fetchall()

            def run_dict(r):
                d = dict(r)
                for k in ("summary_json", "config_snapshot"):
                    if d.get(k):
                        try:
                            d[k] = json.loads(d[k])
                        except Exception:
                            pass
                return d

            r1d = run_dict(r1)
            r2d = run_dict(r2)
            ops1_list = [dict(o) for o in ops1]
            ops2_list = [dict(o) for o in ops2]

            # Build summary comparison
            def _sum(ops, field):
                return sum(o.get(field, 0) or 0 for o in ops)
            def _avg(ops, field):
                vals = [o.get(field, 0) or 0 for o in ops if (o.get(field) or 0) > 0]
                return sum(vals) / len(vals) if vals else 0

            summary = [
                {"metric": "Total Requests", "run1": _sum(ops1_list, "request_count"), "run2": _sum(ops2_list, "request_count"), "lower_is_better": False},
                {"metric": "Total Failures", "run1": _sum(ops1_list, "failure_count"), "run2": _sum(ops2_list, "failure_count"), "lower_is_better": True},
                {"metric": "Avg Response (ms)", "run1": _avg(ops1_list, "avg_response_ms"), "run2": _avg(ops2_list, "avg_response_ms"), "lower_is_better": True},
                {"metric": "P50 (ms)", "run1": _avg(ops1_list, "p50_response_ms"), "run2": _avg(ops2_list, "p50_response_ms"), "lower_is_better": True},
                {"metric": "P95 (ms)", "run1": _avg(ops1_list, "p95_response_ms"), "run2": _avg(ops2_list, "p95_response_ms"), "lower_is_better": True},
                {"metric": "P99 (ms)", "run1": _avg(ops1_list, "p99_response_ms"), "run2": _avg(ops2_list, "p99_response_ms"), "lower_is_better": True},
            ]

            # Build per-operation comparison
            ops1_by_name = {o["operation_name"]: o for o in ops1_list}
            ops2_by_name = {o["operation_name"]: o for o in ops2_list}
            all_op_names = sorted(set(list(ops1_by_name.keys()) + list(ops2_by_name.keys())))

            per_op = []
            for name in all_op_names:
                o1 = ops1_by_name.get(name, {})
                o2 = ops2_by_name.get(name, {})
                per_op.append({
                    "name": name,
                    "run1_avg": o1.get("avg_response_ms"),
                    "run2_avg": o2.get("avg_response_ms"),
                    "run1_p95": o1.get("p95_response_ms"),
                    "run2_p95": o2.get("p95_response_ms"),
                    "run1_requests": o1.get("request_count", 0),
                    "run2_requests": o2.get("request_count", 0),
                    "run1_failures": o1.get("failure_count", 0),
                    "run2_failures": o2.get("failure_count", 0),
                })

            return {
                "run1": r1d,
                "run2": r2d,
                "summary": summary,
                "operations": per_op,
                "operations1": ops1_list,
                "operations2": ops2_list,
            }

        @self.router.get("/trends/{config_id}")
        async def get_trends(config_id: str, request: Request, limit: int = 30):
            require_auth(request)
            db = get_db()
            runs = db.execute(
                "SELECT id, name, status, started_at, completed_at, summary_json FROM test_runs "
                "WHERE config_id = ? AND status = 'completed' ORDER BY started_at DESC LIMIT ?",
                (config_id, limit),
            ).fetchall()

            trend_data = []
            for r in reversed(runs):
                entry = {"run_id": r["id"], "name": r["name"], "started_at": r["started_at"]}
                if r["summary_json"]:
                    try:
                        entry["summary"] = json.loads(r["summary_json"])
                    except Exception:
                        entry["summary"] = {}
                else:
                    entry["summary"] = {}
                # get per-op stats
                ops = db.execute(
                    "SELECT operation_name, avg_response_ms, p50_response_ms, p90_response_ms, p95_response_ms, p99_response_ms, tps_actual, request_count, failure_count "
                    "FROM operation_results WHERE run_id = ?",
                    (r["id"],),
                ).fetchall()
                entry["operations"] = [dict(o) for o in ops]
                trend_data.append(entry)

            return {"config_id": config_id, "trends": trend_data}
