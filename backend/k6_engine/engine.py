"""k6 engine — lifecycle manager, subprocess, JSON metrics parsing."""

import json
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

from backend.config import get_settings
from backend.plugins.storage_plugin import get_db
from backend.k6_engine.script_generator import generate_script

_active_runs: Dict[str, dict] = {}
_lock = threading.Lock()


def _get_runs_dir() -> Path:
    settings = get_settings()
    return Path(settings.DB_PATH).parent / "runs"


def _find_k6() -> str:
    """Find the k6 binary."""
    settings = get_settings()
    if settings.K6_BINARY_PATH:
        return settings.K6_BINARY_PATH

    # Check .venv/bin/k6
    venv_k6 = Path(__file__).parent.parent.parent / ".venv" / "bin" / "k6"
    if venv_k6.exists():
        return str(venv_k6)

    # Check system path
    k6_path = shutil.which("k6")
    if k6_path:
        return k6_path

    raise RuntimeError("k6 binary not found. Install k6 or set K6_BINARY_PATH.")


def start_run(config: dict, user: str) -> dict:
    """Start a new k6 test run."""
    settings = get_settings()

    with _lock:
        active_count = sum(1 for r in _active_runs.values() if r["status"] == "running")
        if active_count >= settings.MAX_CONCURRENT_RUNS:
            raise RuntimeError(f"Max concurrent runs ({settings.MAX_CONCURRENT_RUNS}) reached")

    k6_binary = _find_k6()
    run_id = str(uuid.uuid4())
    run_dir = _get_runs_dir() / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # Resolve auth headers
    auth_headers = {}
    auth_provider_id = config.get("auth_provider_id")
    if auth_provider_id:
        try:
            from backend.plugins.authproviders_plugin import get_auth_header
            headers = get_auth_header(auth_provider_id)
            if headers:
                auth_headers = headers
        except Exception:
            pass

    config["auth_headers"] = auth_headers

    # Generate k6 script
    script = generate_script(config)
    script_path = run_dir / "test.js"
    with open(script_path, "w") as f:
        f.write(script)

    metrics_path = run_dir / "metrics.json"

    # Create DB record
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    gp = config.get("global_params", {})
    db.execute(
        "INSERT INTO test_runs (id, config_id, name, status, started_at, user_count, ramp_up_sec, duration_sec, "
        "host, platform, config_snapshot, engine, debug_mode, cleanup_on_stop, environment_id, created_by) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            run_id, config.get("config_id"), config.get("name", f"k6 Run {run_id[:8]}"),
            "running", now, gp.get("user_count", 10), gp.get("ramp_up_sec", 10),
            gp.get("duration_sec", 60), gp.get("host", ""), gp.get("platform", ""),
            json.dumps(config), "k6", int(config.get("debug_mode", False)),
            int(config.get("cleanup_on_stop", False)), gp.get("environment_id"), user,
        ),
    )
    db.commit()

    # Spawn k6 subprocess
    proc = subprocess.Popen(
        [k6_binary, "run", "--out", f"json={metrics_path.resolve()}", str(script_path.resolve())],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(run_dir.resolve()),
    )

    run_info = {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "process": proc,
        "status": "running",
        "stats_deque": deque(maxlen=300),
        "errors": deque(maxlen=500),
        "started_at": time.time(),
    }

    with _lock:
        _active_runs[run_id] = run_info

    # Start reader thread
    reader = threading.Thread(target=_metric_reader, args=(run_id,), daemon=True)
    reader.start()

    return {"run_id": run_id, "status": "running"}


def stop_run(run_id: str) -> dict:
    """Kill the k6 process."""
    with _lock:
        run = _active_runs.get(run_id)

    if run and run["process"].poll() is None:
        run["process"].terminate()
        return {"run_id": run_id, "status": "stopping"}

    return {"run_id": run_id, "status": "not_found"}


def get_status(run_id: str) -> dict:
    """Get current stats for a k6 test."""
    with _lock:
        run = _active_runs.get(run_id)

    if run:
        stats = list(run["stats_deque"])
        latest = stats[-1] if stats else {}
        return {
            "run_id": run_id,
            "status": run["status"],
            "latest": latest,
            "history": stats[-60:],
            "errors": list(run["errors"])[-20:],
        }

    return {"run_id": run_id, "status": "unknown", "latest": {}, "history": [], "errors": []}


def _metric_reader(run_id: str):
    """Background thread parsing k6 JSON metrics output."""
    with _lock:
        run = _active_runs.get(run_id)
    if not run:
        return

    run_dir = Path(run["run_dir"])
    metrics_path = run_dir / "metrics.json"
    last_pos = 0
    op_stats = {}

    while True:
        time.sleep(2)

        # Parse new metrics lines
        if metrics_path.exists():
            try:
                with open(metrics_path) as f:
                    f.seek(last_pos)
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                            metric = entry.get("metric", "")
                            tags = entry.get("data", {}).get("tags", {})
                            value = entry.get("data", {}).get("value", 0)
                            name = tags.get("name", "default")

                            if name not in op_stats:
                                op_stats[name] = {
                                    "request_count": 0, "failure_count": 0,
                                    "total_ms": 0, "min_ms": float("inf"), "max_ms": 0,
                                    "total_response_bytes": 0, "total_request_bytes": 0,
                                }

                            if metric == "http_req_duration":
                                op_stats[name]["request_count"] += 1
                                op_stats[name]["total_ms"] += value
                                op_stats[name]["min_ms"] = min(op_stats[name]["min_ms"], value)
                                op_stats[name]["max_ms"] = max(op_stats[name]["max_ms"], value)

                            elif metric == "http_req_failed" and value == 1:
                                op_stats[name]["failure_count"] += 1

                            elif metric == "http_req_receiving":
                                op_stats[name]["total_response_bytes"] += int(value)

                            elif metric == "http_req_sending":
                                op_stats[name]["total_request_bytes"] += int(value)

                        except Exception:
                            pass
                    last_pos = f.tell()
            except Exception:
                pass

        # Build stats snapshot
        snapshot = {
            "timestamp": time.time(),
            "elapsed_sec": round(time.time() - run["started_at"], 1),
            "operations": {},
            "total_requests": 0,
            "total_failures": 0,
            "total_rps": 0,
        }

        elapsed = max(1, time.time() - run["started_at"])
        for name, st in op_stats.items():
            cnt = st["request_count"]
            avg = round(st["total_ms"] / cnt, 2) if cnt > 0 else 0
            snapshot["operations"][name] = {
                "request_count": cnt,
                "failure_count": st["failure_count"],
                "avg_response_ms": avg,
                "min_response_ms": round(st["min_ms"], 2) if st["min_ms"] != float("inf") else 0,
                "max_response_ms": round(st["max_ms"], 2),
                "tps_actual": round(cnt / elapsed, 2),
                "total_response_bytes": st.get("total_response_bytes", 0),
                "total_request_bytes": st.get("total_request_bytes", 0),
                "avg_response_bytes": round(st.get("total_response_bytes", 0) / cnt, 0) if cnt > 0 else 0,
                "avg_request_bytes": round(st.get("total_request_bytes", 0) / cnt, 0) if cnt > 0 else 0,
            }
            snapshot["total_requests"] += cnt
            snapshot["total_failures"] += st["failure_count"]
            snapshot["total_rps"] += round(cnt / elapsed, 2)

        snapshot["total_rps"] = round(snapshot["total_rps"], 2)
        run["stats_deque"].append(snapshot)

        # Check if process ended
        proc = run["process"]
        if proc.poll() is not None:
            run["status"] = "completed" if proc.returncode == 0 else "failed"

            # Persist to DB
            try:
                db = get_db()
                now_str = datetime.now(timezone.utc).isoformat()
                final_summary = json.dumps(snapshot)

                stderr_output = ""
                try:
                    stderr_output = proc.stderr.read().decode(errors="replace")[:5000]
                except Exception:
                    pass

                status = "completed" if proc.returncode == 0 else "failed"

                # Build chart snapshots
                chart_data = _build_chart_snapshots(run)

                db.execute(
                    "UPDATE test_runs SET status=?, completed_at=?, summary_json=?, error_log=?, chart_snapshots=? WHERE id=?",
                    (status, now_str, final_summary, stderr_output, chart_data, run_id),
                )

                for name, st in op_stats.items():
                    cnt = st["request_count"]
                    avg = round(st["total_ms"] / cnt, 2) if cnt > 0 else 0
                    db.execute(
                        "INSERT INTO operation_results (run_id, operation_name, operation_type, request_count, failure_count, "
                        "avg_response_ms, min_response_ms, max_response_ms, total_response_bytes, total_request_bytes, "
                        "avg_response_bytes, avg_request_bytes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                        (run_id, name, "query", cnt, st["failure_count"], avg,
                         round(st["min_ms"], 2) if st["min_ms"] != float("inf") else 0,
                         round(st["max_ms"], 2),
                         st.get("total_response_bytes", 0), st.get("total_request_bytes", 0),
                         round(st.get("total_response_bytes", 0) / cnt, 0) if cnt > 0 else 0,
                         round(st.get("total_request_bytes", 0) / cnt, 0) if cnt > 0 else 0),
                    )
                db.commit()

                # Prune old chart data
                _prune_chart_history(db)
            except Exception as e:
                print(f"[k6_engine] Failed to persist results: {e}")
            break


def _build_chart_snapshots(run: dict) -> str | None:
    """Build a size-optimized JSON string of chart data from stats_deque."""
    snapshots = list(run.get("stats_deque", []))
    if not snapshots:
        return None
    compact = []
    for s in snapshots:
        point = {
            "t": round(s.get("elapsed_sec", 0), 1),
            "rps": round(s.get("total_rps", 0), 2),
            "req": s.get("total_requests", 0),
            "fail": s.get("total_failures", 0),
        }
        ops = s.get("operations", {})
        if ops:
            lat = {}
            for name, st in ops.items():
                lat[name] = round(st.get("avg_response_ms", 0), 1)
            point["lat"] = lat
        compact.append(point)
    return json.dumps(compact, separators=(",", ":"))


def _prune_chart_history(db):
    """Clear chart_snapshots for runs beyond the configurable retention limit."""
    try:
        settings = get_settings()
        limit = settings.CHART_HISTORY_RUNS
        keep_rows = db.execute(
            "SELECT id FROM test_runs WHERE chart_snapshots IS NOT NULL AND status IN ('completed','failed') "
            "ORDER BY started_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        keep_ids = {r["id"] for r in keep_rows}
        if keep_ids:
            placeholders = ",".join("?" * len(keep_ids))
            db.execute(
                f"UPDATE test_runs SET chart_snapshots = NULL "
                f"WHERE chart_snapshots IS NOT NULL AND id NOT IN ({placeholders})",
                list(keep_ids),
            )
            db.commit()
    except Exception:
        pass
