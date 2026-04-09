"""Cleanup plugin — execute delete mutations for test data cleanup."""

import json
import uuid
import threading
import time
from datetime import datetime, timezone

import httpx
from fastapi import HTTPException, Request

from backend.core.plugin_base import PluginBase
from backend.plugins.storage_plugin import get_db
from backend.plugins.auth_plugin import require_auth, require_role

_cleanup_threads = {}


def _run_cleanup(job_id: str, run_id: str, host: str, graphql_path: str, operations: list, auth_header: str = ""):
    """Background thread that executes delete mutations."""
    import sqlite3, threading as th
    from backend.config import get_settings

    settings = get_settings()
    db = sqlite3.connect(settings.DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")

    try:
        db.execute("UPDATE cleanup_jobs SET status='running' WHERE id=?", (job_id,))
        db.commit()

        completed = 0
        failed = 0
        errors = []
        url = f"{host.rstrip('/')}{graphql_path}"
        headers = {"Content-Type": "application/json"}
        if auth_header:
            headers["Authorization"] = auth_header

        for op in operations:
            try:
                payload = {"query": op.get("query", ""), "variables": op.get("variables", {})}
                resp = httpx.post(url, json=payload, headers=headers, timeout=30)
                if resp.status_code == 200:
                    body = resp.json()
                    if "errors" in body:
                        failed += 1
                        errors.append(f"{op.get('name','?')}: {body['errors'][0].get('message','unknown')}")
                    else:
                        completed += 1
                else:
                    failed += 1
                    errors.append(f"{op.get('name','?')}: HTTP {resp.status_code}")
            except Exception as e:
                failed += 1
                errors.append(f"{op.get('name','?')}: {str(e)}")

            db.execute(
                "UPDATE cleanup_jobs SET completed_ops=?, failed_ops=? WHERE id=?",
                (completed, failed, job_id),
            )
            db.commit()
            time.sleep(0.1)  # Rate limit

        now = datetime.now(timezone.utc).isoformat()
        status = "completed" if failed == 0 else "failed"
        db.execute(
            "UPDATE cleanup_jobs SET status=?, completed_ops=?, failed_ops=?, error_details=?, completed_at=? WHERE id=?",
            (status, completed, failed, json.dumps(errors) if errors else None, now, job_id),
        )
        db.commit()
    except Exception as e:
        now = datetime.now(timezone.utc).isoformat()
        db.execute(
            "UPDATE cleanup_jobs SET status='failed', error_details=?, completed_at=? WHERE id=?",
            (str(e), now, job_id),
        )
        db.commit()
    finally:
        db.close()


class CleanupPlugin(PluginBase):
    @property
    def name(self) -> str:
        return "cleanup"

    @property
    def description(self) -> str:
        return "Execute delete mutations for test data cleanup, rate-limited"

    def _register_routes(self):
        @self.router.post("/start/{run_id}")
        async def start_cleanup(run_id: str, request: Request):
            require_role(request, "maintainer")
            db = get_db()

            run = db.execute("SELECT * FROM test_runs WHERE id = ?", (run_id,)).fetchone()
            if not run:
                raise HTTPException(404, "Run not found")

            config_snapshot = {}
            if run["config_snapshot"]:
                try:
                    config_snapshot = json.loads(run["config_snapshot"])
                except Exception:
                    pass

            # Find delete/cleanup mutations
            ops = config_snapshot.get("operations", [])
            delete_ops = [o for o in ops if o.get("type") == "mutation" and any(
                kw in o.get("name", "").lower() for kw in ("delete", "remove", "cancel")
            )]

            if not delete_ops:
                raise HTTPException(400, "No delete/cleanup mutations found in config")

            job_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc).isoformat()
            db.execute(
                "INSERT INTO cleanup_jobs (id, run_id, status, total_ops, created_at) VALUES (?,?,?,?,?)",
                (job_id, run_id, "pending", len(delete_ops), now),
            )
            db.commit()

            host = config_snapshot.get("global_params", {}).get("host", run["host"] or "")
            gpath = config_snapshot.get("global_params", {}).get("graphql_path", "/graphql")

            t = threading.Thread(
                target=_run_cleanup,
                args=(job_id, run_id, host, gpath, delete_ops),
                daemon=True,
            )
            _cleanup_threads[job_id] = t
            t.start()

            return {"job_id": job_id, "status": "started", "total_ops": len(delete_ops)}

        @self.router.get("/status/{job_id}")
        async def cleanup_status(job_id: str, request: Request):
            require_auth(request)
            db = get_db()
            row = db.execute("SELECT * FROM cleanup_jobs WHERE id = ?", (job_id,)).fetchone()
            if not row:
                raise HTTPException(404, "Cleanup job not found")
            result = dict(row)
            if result.get("error_details"):
                try:
                    result["error_details"] = json.loads(result["error_details"])
                except Exception:
                    pass
            return result

        @self.router.get("/jobs")
        async def list_cleanup_jobs(request: Request):
            require_auth(request)
            db = get_db()
            rows = db.execute("SELECT * FROM cleanup_jobs ORDER BY created_at DESC LIMIT 50").fetchall()
            return {"jobs": [dict(r) for r in rows]}
