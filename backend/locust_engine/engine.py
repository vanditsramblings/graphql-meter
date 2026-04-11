"""Locust engine — lifecycle manager, subprocess spawn, file reader thread, stats polling."""

import json
import os
import subprocess
import sys
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from backend.config import get_settings
from backend.plugins.storage_plugin import get_db

_active_runs: Dict[str, dict] = {}
_lock = threading.Lock()


def _get_runs_dir() -> Path:
    settings = get_settings()
    return Path(settings.DB_PATH).parent / "runs"


def start_run(config: dict, user: str) -> dict:
    """Start a new Locust test run."""
    settings = get_settings()

    with _lock:
        active_count = sum(1 for r in _active_runs.values() if r["status"] == "running")
        if active_count >= settings.MAX_CONCURRENT_RUNS:
            raise RuntimeError(f"Max concurrent runs ({settings.MAX_CONCURRENT_RUNS}) reached")

    run_id = str(uuid.uuid4())
    run_dir = _get_runs_dir() / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # Write config for worker
    config_path = run_dir / "config.json"

    # Resolve auth provider headers if specified
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

    worker_config = {
        "global_params": config.get("global_params", {}),
        "operations": config.get("operations", []),
        "debug_mode": config.get("debug_mode", False),
        "auth_headers": auth_headers,
    }
    with open(config_path, "w") as f:
        json.dump(worker_config, f)

    # Create DB record
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    gp = config.get("global_params", {})
    db.execute(
        "INSERT INTO test_runs (id, config_id, name, status, started_at, user_count, ramp_up_sec, duration_sec, "
        "host, platform, config_snapshot, engine, debug_mode, cleanup_on_stop, environment_id, created_by) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            run_id, config.get("config_id"), config.get("name", f"Run {run_id[:8]}"),
            "running", now, gp.get("user_count", 10), gp.get("ramp_up_sec", 10),
            gp.get("duration_sec", 60), gp.get("host", ""), gp.get("platform", ""),
            json.dumps(config), "locust", int(config.get("debug_mode", False)),
            int(config.get("cleanup_on_stop", False)), gp.get("environment_id"), user,
        ),
    )
    db.commit()

    # Spawn worker subprocess
    worker_path = str(Path(__file__).parent / "worker.py")
    python_path = sys.executable
    proc = subprocess.Popen(
        [python_path, worker_path, str(run_dir)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(Path(__file__).parent.parent.parent),
    )

    run_info = {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "process": proc,
        "status": "running",
        "stats_deque": deque(maxlen=300),
        "errors": deque(maxlen=500),
        "debug_logs": deque(maxlen=200),
        "started_at": time.time(),
    }

    with _lock:
        _active_runs[run_id] = run_info

    # Start file reader thread
    reader = threading.Thread(target=_file_reader, args=(run_id,), daemon=True)
    reader.start()

    return {"run_id": run_id, "status": "running"}


def stop_run(run_id: str) -> dict:
    """Signal a running test to stop."""
    with _lock:
        run = _active_runs.get(run_id)

    if run and run["status"] == "running":
        stop_file = Path(run["run_dir"]) / "stop"
        stop_file.touch()
        return {"run_id": run_id, "status": "stopping"}

    # Try DB fallback
    db = get_db()
    row = db.execute("SELECT status FROM test_runs WHERE id = ?", (run_id,)).fetchone()
    if row and row["status"] == "running":
        run_dir = _get_runs_dir() / run_id
        (run_dir / "stop").touch()
        return {"run_id": run_id, "status": "stopping"}

    return {"run_id": run_id, "status": "not_found"}


def get_status(run_id: str) -> dict:
    """Get current live stats for a running test."""
    with _lock:
        run = _active_runs.get(run_id)

    if run:
        stats = list(run["stats_deque"])
        latest = stats[-1] if stats else {}
        return {
            "run_id": run_id,
            "status": run["status"],
            "latest": latest,
            "history": stats[-60:],  # Last 2 minutes at 2s intervals
            "errors": list(run["errors"])[-20:],
            "debug_logs": list(run["debug_logs"])[-50:],
        }

    # Check filesystem
    run_dir = _get_runs_dir() / run_id
    stats_path = run_dir / "stats.json"
    done_path = run_dir / "done.json"

    result = {"run_id": run_id, "status": "unknown", "latest": {}, "history": [], "errors": []}

    if done_path.exists():
        try:
            with open(done_path) as f:
                result["latest"] = json.load(f)
            result["status"] = "completed"
        except Exception:
            pass
    elif stats_path.exists():
        try:
            with open(stats_path) as f:
                result["latest"] = json.load(f)
            result["status"] = "running"
        except Exception:
            pass

    return result


def _file_reader(run_id: str):
    """Background thread that polls stats and error files."""
    with _lock:
        run = _active_runs.get(run_id)
    if not run:
        return

    run_dir = Path(run["run_dir"])
    stats_path = run_dir / "stats.json"
    errors_path = run_dir / "errors.jsonl"
    done_path = run_dir / "done.json"
    debug_path = run_dir / "debug.jsonl"
    last_error_pos = 0
    last_debug_pos = 0

    while True:
        time.sleep(2)

        # Read stats
        if stats_path.exists():
            try:
                with open(stats_path) as f:
                    data = json.load(f)
                run["stats_deque"].append(data)
            except Exception:
                pass

        # Read new errors
        if errors_path.exists():
            try:
                with open(errors_path) as f:
                    f.seek(last_error_pos)
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                run["errors"].append(json.loads(line))
                            except Exception:
                                run["errors"].append({"message": line})
                    last_error_pos = f.tell()
            except Exception:
                pass

        # Read new debug logs
        if debug_path.exists():
            try:
                with open(debug_path) as f:
                    f.seek(last_debug_pos)
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                run["debug_logs"].append(json.loads(line))
                            except Exception:
                                pass
                    last_debug_pos = f.tell()
            except Exception:
                pass

        # Check if process ended
        proc = run["process"]
        if proc.poll() is not None:
            # Process exited
            run["status"] = "completed"

            # Read final results
            if done_path.exists():
                try:
                    with open(done_path) as f:
                        final = json.load(f)
                    _persist_results(run_id, final)
                except Exception:
                    pass

            # Update DB
            try:
                db = get_db()
                now = datetime.now(timezone.utc).isoformat()
                errors_text = ""
                if errors_path.exists():
                    try:
                        errors_text = errors_path.read_text()
                    except Exception:
                        pass
                status = "completed" if proc.returncode == 0 else "failed"
                db.execute(
                    "UPDATE test_runs SET status=?, completed_at=?, error_log=? WHERE id=?",
                    (status, now, errors_text, run_id),
                )
                db.commit()
                run["status"] = status
            except Exception:
                pass
            break

        # Check if still active
        with _lock:
            if run_id not in _active_runs:
                break


def _persist_results(run_id: str, final: dict):
    """Save final operation results to the database."""
    try:
        db = get_db()
        summary = json.dumps(final)
        db.execute("UPDATE test_runs SET summary_json = ? WHERE id = ?", (summary, run_id))

        for op_name, op_stats in final.get("operations", {}).items():
            db.execute(
                "INSERT INTO operation_results (run_id, operation_name, operation_type, request_count, failure_count, "
                "avg_response_ms, min_response_ms, max_response_ms, p50_response_ms, p90_response_ms, "
                "p95_response_ms, p99_response_ms, total_response_bytes, total_request_bytes, "
                "avg_response_bytes, avg_request_bytes, stats_json) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    run_id, op_name, "query",
                    op_stats.get("request_count", 0), op_stats.get("failure_count", 0),
                    op_stats.get("avg_response_ms", 0), op_stats.get("min_response_ms", 0),
                    op_stats.get("max_response_ms", 0), op_stats.get("p50_response_ms", 0),
                    op_stats.get("p90_response_ms", 0), op_stats.get("p95_response_ms", 0),
                    op_stats.get("p99_response_ms", 0),
                    op_stats.get("total_response_bytes", 0), op_stats.get("total_request_bytes", 0),
                    op_stats.get("avg_response_bytes", 0), op_stats.get("avg_request_bytes", 0),
                    json.dumps(op_stats),
                ),
            )
        db.commit()
    except Exception as e:
        print(f"[locust_engine] Failed to persist results: {e}")
