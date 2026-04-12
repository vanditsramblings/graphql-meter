"""k6 engine — lifecycle manager, subprocess, JSON metrics parsing."""

import bisect
import json
import math
import os
import signal
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
from backend.k6_manager import ensure_k6

_active_runs: Dict[str, dict] = {}
_lock = threading.Lock()


def _percentile(sorted_values: list, pct: float) -> float:
    """Compute percentile from a sorted list of values."""
    if not sorted_values:
        return 0
    k = (len(sorted_values) - 1) * pct
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_values[int(k)]
    return sorted_values[f] * (c - k) + sorted_values[c] * (k - f)


def _get_runs_dir() -> Path:
    settings = get_settings()
    return Path(settings.DB_PATH).parent / "runs"


def _find_k6() -> str:
    """Find the k6 binary, auto-downloading if necessary."""
    return ensure_k6()


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

    # Redirect stderr to file to avoid pipe blocking on large output
    stderr_path = run_dir / "stderr.log"
    stderr_file = open(stderr_path, "w")

    # Spawn k6 subprocess (stdout not needed — handleSummary writes to file)
    proc = subprocess.Popen(
        [k6_binary, "run", "--out", f"json={metrics_path.resolve()}", str(script_path.resolve())],
        stdout=subprocess.DEVNULL,
        stderr=stderr_file,
        cwd=str(run_dir.resolve()),
        start_new_session=True,
    )

    run_info = {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "process": proc,
        "status": "running",
        "stats_deque": deque(maxlen=300),
        "errors": deque(maxlen=500),
        "started_at": time.time(),
        "stderr_file": stderr_file,
    }

    with _lock:
        _active_runs[run_id] = run_info

    # Start reader thread
    reader = threading.Thread(target=_metric_reader, args=(run_id,), daemon=True)
    reader.start()

    return {"run_id": run_id, "status": "running"}


def _kill_watchdog(run: dict):
    """Wait for process exit, force-kill if it doesn't exit in time."""
    proc = run["process"]
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (OSError, ProcessLookupError):
            try:
                proc.kill()
            except Exception:
                pass


def stop_run(run_id: str) -> dict:
    """Stop the k6 process gracefully, force-kill if needed."""
    with _lock:
        run = _active_runs.get(run_id)

    if run and run["process"].poll() is None:
        run["_stopped"] = True
        try:
            os.killpg(os.getpgid(run["process"].pid), signal.SIGTERM)
        except (OSError, ProcessLookupError):
            run["process"].terminate()
        # Watchdog thread: force-kill after 10s if still alive
        threading.Thread(target=_kill_watchdog, args=(run,), daemon=True).start()
        return {"run_id": run_id, "status": "stopping"}

    return {"run_id": run_id, "status": "not_found"}


def get_status(run_id: str) -> dict:
    """Get current stats for a k6 test."""
    with _lock:
        run = _active_runs.get(run_id)

    if run:
        stats = list(run["stats_deque"])
        latest = stats[-1] if stats else {}
        # Build compact chart data from all accumulated snapshots for live persistence
        chart_data = []
        for s in stats:
            point = {
                "t": round(s.get("elapsed_sec", 0), 1),
                "rps": round(s.get("total_rps", 0), 2),
                "req": s.get("total_requests", 0),
                "fail": s.get("total_failures", 0),
            }
            ops = s.get("operations", {})
            if ops:
                lat = {}
                op_rps = {}
                for name, st in ops.items():
                    lat[name] = round(st.get("avg_response_ms", 0), 1)
                    op_rps[name] = round(st.get("tps_actual", 0), 2)
                point["lat"] = lat
                point["op_rps"] = op_rps
            chart_data.append(point)
        return {
            "run_id": run_id,
            "status": run["status"],
            "latest": latest,
            "history": stats[-60:],
            "chart_data": chart_data,
            "errors": list(run["errors"])[-20:],
        }

    return {"run_id": run_id, "status": "unknown", "latest": {}, "history": [], "chart_data": [], "errors": []}


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

    # Build operation type lookup from config
    config_path = run_dir / "test.js"
    op_type_map = {}
    try:
        config_snapshot_row = get_db().execute(
            "SELECT config_snapshot FROM test_runs WHERE id = ?", (run_id,)
        ).fetchone()
        if config_snapshot_row and config_snapshot_row["config_snapshot"]:
            cfg = json.loads(config_snapshot_row["config_snapshot"]) if isinstance(config_snapshot_row["config_snapshot"], str) else config_snapshot_row["config_snapshot"]
            for op in cfg.get("operations", []):
                op_type_map[op["name"]] = op.get("type", "query")
    except Exception:
        pass

    while True:
        time.sleep(2)

        # Check if stopped before processing
        if run.get("_stopped") and run["process"].poll() is not None:
            run["status"] = "stopped"
            try:
                run["stderr_file"].close()
            except Exception:
                pass
            try:
                db = get_db()
                now_str = datetime.now(timezone.utc).isoformat()
                snapshot = _build_snapshot(op_stats, run, op_type_map)
                final_summary = json.dumps(snapshot)
                chart_data = _build_chart_snapshots(run)
                db.execute(
                    "UPDATE test_runs SET status=?, completed_at=?, summary_json=?, chart_snapshots=? WHERE id=?",
                    ("stopped", now_str, final_summary, chart_data, run_id),
                )
                _persist_operation_results(db, run_id, op_stats, op_type_map)
                db.commit()
                _prune_chart_history(db)
            except Exception as e:
                print(f"[k6_engine] Failed to persist stopped results: {e}")
            break

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
                            _process_metric_entry(entry, op_stats, run)
                        except Exception:
                            pass
                    last_pos = f.tell()
            except Exception:
                pass

        # Build stats snapshot
        snapshot = _build_snapshot(op_stats, run, op_type_map)
        run["stats_deque"].append(snapshot)

        # Check if process ended
        proc = run["process"]
        if proc.poll() is not None:
            if run.get("_stopped"):
                run["status"] = "stopped"
            else:
                run["status"] = "completed" if proc.returncode == 0 else "failed"

            # Parse the handleSummary output from file for final percentiles
            summary_path = run_dir / "summary.json"
            try:
                if summary_path.exists():
                    summary_text = summary_path.read_text(errors="replace")
                    if summary_text.strip():
                        _parse_summary_output(summary_text, op_stats)
            except Exception:
                pass

            # Close stderr file handle and read for error analysis
            try:
                run["stderr_file"].close()
            except Exception:
                pass

            # Persist to DB
            try:
                db = get_db()
                now_str = datetime.now(timezone.utc).isoformat()
                final_snapshot = _build_snapshot(op_stats, run, op_type_map)
                final_summary = json.dumps(final_snapshot)

                stderr_output = ""
                stderr_path = run_dir / "stderr.log"
                try:
                    if stderr_path.exists():
                        stderr_output = stderr_path.read_text(errors="replace")[:5000]
                except Exception:
                    pass

                # Collect errors from stderr (k6 prints warnings/errors there)
                if stderr_output:
                    for line in stderr_output.strip().split("\n"):
                        line = line.strip()
                        if line and ("WARN" in line or "error" in line.lower() or "failed" in line.lower()):
                            run["errors"].append({"message": line, "timestamp": time.time()})

                status = run["status"]
                chart_data = _build_chart_snapshots(run)

                # Build errors text for DB
                errors_text = "\n".join(json.dumps(e) for e in list(run["errors"]))

                db.execute(
                    "UPDATE test_runs SET status=?, completed_at=?, summary_json=?, error_log=?, chart_snapshots=? WHERE id=?",
                    (status, now_str, final_summary, errors_text, chart_data, run_id),
                )

                _persist_operation_results(db, run_id, op_stats, op_type_map)
                db.commit()
                _prune_chart_history(db)
            except Exception as e:
                print(f"[k6_engine] Failed to persist results: {e}")
            break


def _process_metric_entry(entry: dict, op_stats: dict, run: dict):
    """Process a single k6 JSON metrics line."""
    entry_type = entry.get("type", "")
    metric = entry.get("metric", "")
    data = entry.get("data", {})
    tags = data.get("tags", {})
    value = data.get("value", 0)
    name = tags.get("name", "")

    # Skip aggregate entries without a named tag (these are the "default" entries)
    if not name:
        return

    if name not in op_stats:
        op_stats[name] = {
            "request_count": 0, "failure_count": 0,
            "total_ms": 0, "min_ms": float("inf"), "max_ms": 0,
            "durations": [],  # sorted list for percentile computation
            "total_data_received": 0, "total_data_sent": 0,
        }

    if metric == "http_req_duration" and entry_type == "Point":
        op_stats[name]["request_count"] += 1
        op_stats[name]["total_ms"] += value
        op_stats[name]["min_ms"] = min(op_stats[name]["min_ms"], value)
        op_stats[name]["max_ms"] = max(op_stats[name]["max_ms"], value)
        bisect.insort(op_stats[name]["durations"], value)

    elif metric == "http_req_failed" and entry_type == "Point" and value == 1:
        op_stats[name]["failure_count"] += 1
        # Log failure as error
        status = tags.get("status", "")
        error_url = tags.get("url", "")
        expected_response = tags.get("expected_response", "")
        run["errors"].append({
            "timestamp": time.time(),
            "operation": name,
            "message": f"Request failed: status={status}, expected_response={expected_response}",
            "status_code": status,
        })

    elif metric == "http_req_receiving" and entry_type == "Point":
        # This is time in ms, not bytes - skip for byte tracking
        pass

    elif metric == "data_received" and entry_type == "Point":
        op_stats[name]["total_data_received"] += int(value)

    elif metric == "data_sent" and entry_type == "Point":
        op_stats[name]["total_data_sent"] += int(value)


def _build_snapshot(op_stats: dict, run: dict, op_type_map: dict) -> dict:
    """Build a stats snapshot from accumulated op_stats."""
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
        durations = st["durations"]
        snapshot["operations"][name] = {
            "operation_type": op_type_map.get(name, "query"),
            "request_count": cnt,
            "failure_count": st["failure_count"],
            "avg_response_ms": avg,
            "min_response_ms": round(st["min_ms"], 2) if st["min_ms"] != float("inf") else 0,
            "max_response_ms": round(st["max_ms"], 2),
            "p50_response_ms": round(_percentile(durations, 0.5), 2) if durations else None,
            "p90_response_ms": round(_percentile(durations, 0.9), 2) if durations else None,
            "p95_response_ms": round(_percentile(durations, 0.95), 2) if durations else None,
            "p99_response_ms": round(_percentile(durations, 0.99), 2) if durations else None,
            "tps_actual": round(cnt / elapsed, 2),
            "total_response_bytes": st.get("total_data_received", 0),
            "total_request_bytes": st.get("total_data_sent", 0),
            "avg_response_bytes": round(st.get("total_data_received", 0) / cnt, 0) if cnt > 0 else 0,
            "avg_request_bytes": round(st.get("total_data_sent", 0) / cnt, 0) if cnt > 0 else 0,
        }
        snapshot["total_requests"] += cnt
        snapshot["total_failures"] += st["failure_count"]
        snapshot["total_rps"] += round(cnt / elapsed, 2)

    snapshot["total_rps"] = round(snapshot["total_rps"], 2)
    return snapshot


def _parse_summary_output(stdout: str, op_stats: dict):
    """Parse k6 handleSummary JSON output for final percentile refinement."""
    try:
        summary = json.loads(stdout)
        # k6 handleSummary provides metrics with percentile data
        metrics = summary.get("metrics", {})
        duration = metrics.get("http_req_duration", {})
        if duration and "values" in duration:
            # These are aggregated values across all requests - useful as fallback
            pass
    except Exception:
        pass


def _persist_operation_results(db, run_id: str, op_stats: dict, op_type_map: dict):
    """Write per-operation results to the operation_results table."""
    for name, st in op_stats.items():
        cnt = st["request_count"]
        avg = round(st["total_ms"] / cnt, 2) if cnt > 0 else 0
        durations = st["durations"]
        db.execute(
            "INSERT INTO operation_results (run_id, operation_name, operation_type, request_count, failure_count, "
            "avg_response_ms, min_response_ms, max_response_ms, p50_response_ms, p90_response_ms, "
            "p95_response_ms, p99_response_ms, total_response_bytes, total_request_bytes, "
            "avg_response_bytes, avg_request_bytes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (run_id, name, op_type_map.get(name, "query"), cnt, st["failure_count"], avg,
             round(st["min_ms"], 2) if st["min_ms"] != float("inf") else 0,
             round(st["max_ms"], 2),
             round(_percentile(durations, 0.5), 2) if durations else None,
             round(_percentile(durations, 0.9), 2) if durations else None,
             round(_percentile(durations, 0.95), 2) if durations else None,
             round(_percentile(durations, 0.99), 2) if durations else None,
             st.get("total_data_received", 0), st.get("total_data_sent", 0),
             round(st.get("total_data_received", 0) / cnt, 0) if cnt > 0 else 0,
             round(st.get("total_data_sent", 0) / cnt, 0) if cnt > 0 else 0),
        )


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
            op_rps = {}
            for name, st in ops.items():
                lat[name] = round(st.get("avg_response_ms", 0), 1)
                op_rps[name] = round(st.get("tps_actual", 0), 2)
            point["lat"] = lat
            point["op_rps"] = op_rps
        compact.append(point)
    return json.dumps(compact, separators=(",", ":"))


def _prune_chart_history(db):
    """Clear chart_snapshots for runs beyond the configurable retention limit."""
    try:
        settings = get_settings()
        limit = settings.CHART_HISTORY_RUNS
        keep_rows = db.execute(
            "SELECT id FROM test_runs WHERE chart_snapshots IS NOT NULL AND status IN ('completed','failed','stopped') "
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
