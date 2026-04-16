"""Locust worker — child process entry point.

This module is executed in a subprocess to avoid gevent/asyncio conflicts.
It reads config.json, runs the Locust environment, and writes stats/errors/done files.
"""

import json
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path


def run_worker(run_dir: str):
    """Main entry point for the child process."""
    # Now safe to import locust (gevent monkey-patching happens here)
    import gevent
    from locust import events
    from locust.env import Environment

    run_path = Path(run_dir)
    config_path = run_path / "config.json"
    stats_path = run_path / "stats.json"
    errors_path = run_path / "errors.jsonl"
    done_path = run_path / "done.json"
    stop_path = run_path / "stop"
    debug_log_path = run_path / "debug.jsonl"

    with open(config_path) as f:
        config = json.load(f)

    global_params = config.get("global_params", {})
    operations = [o for o in config.get("operations", []) if o.get("enabled", True)]
    host = global_params.get("host", "http://localhost:4000")
    graphql_path = global_params.get("graphql_path", "/graphql")
    user_count = global_params.get("user_count", 10)
    ramp_up = global_params.get("ramp_up_sec", 10)
    duration = global_params.get("duration_sec", 60)
    debug_mode = config.get("debug_mode", False)
    auth_headers = config.get("auth_headers", {})

    url = f"{host.rstrip('/')}{graphql_path}"

    def _resolve_placeholder(value, r_val):
        """Resolve {r} placeholders in a value, coercing types where possible."""
        if isinstance(value, str) and "{r}" in value:
            replaced = value.replace("{r}", str(r_val))
            # If the entire value is just the number, try numeric coercion
            try:
                if replaced == str(int(replaced)):
                    return int(replaced)
            except (ValueError, OverflowError):
                pass
            try:
                float(replaced)
                if "." in replaced:
                    return float(replaced)
            except (ValueError, OverflowError):
                pass
            return replaced
        if isinstance(value, dict):
            return {k: _resolve_placeholder(v, r_val) for k, v in value.items()}
        if isinstance(value, list):
            return [_resolve_placeholder(item, r_val) for item in value]
        return value

    def _resolve_variables(vars_dict, r_val):
        """Resolve all {r} placeholders in a variables dictionary."""
        return {k: _resolve_placeholder(v, r_val) for k, v in vars_dict.items()}

    # Build dynamic HttpUser
    from locust import HttpUser, constant_pacing

    task_funcs = {}
    range_counters = {}

    for op in operations:
        op_name = op["name"]
        weight = max(1, int(op.get("tps_percentage", 10)))
        query = op.get("query", "")
        variables = {}
        for v in op.get("variables", []):
            variables[v["name"]] = v.get("value", v.get("default_value", ""))
        delay = op.get("delay_start_sec", 0)
        rstart = op.get("data_range_start", 1)
        rend = op.get("data_range_end", 100)
        range_counters[op_name] = {"current": rstart, "start": rstart, "end": rend}

        def make_task(name, q, vars_, delay_sec, rng_key):
            def op_task(self):
                if delay_sec > 0 and (time.time() - self._start_time) < delay_sec:
                    return
                # Resolve {r} placeholders
                rng = range_counters[rng_key]
                r_val = rng["current"]
                rng["current"] = rng["current"] + 1 if rng["current"] < rng["end"] else rng["start"]

                resolved_vars = _resolve_variables(vars_, r_val)

                payload = {"query": q, "variables": resolved_vars}
                headers = {"Content-Type": "application/json"}
                headers.update(auth_headers)

                with self.client.post(
                    url, json=payload, headers=headers,
                    name=name, catch_response=True
                ) as response:
                    resp_body = None
                    # Track request/response sizes
                    req_size = len(json.dumps(payload).encode('utf-8'))
                    resp_size = len(response.content) if hasattr(response, 'content') else 0
                    _track_size(name, req_size, resp_size)

                    if response.status_code == 200:
                        try:
                            resp_body = response.json()
                            if "errors" in resp_body:
                                msg = resp_body["errors"][0].get("message", "GraphQL error")
                                response.failure(msg)
                                _log_error(name, msg, response.status_code)
                        except Exception:
                            pass
                    else:
                        response.failure(f"HTTP {response.status_code}")
                        _log_error(name, f"HTTP {response.status_code}", response.status_code)
                        try:
                            resp_body = response.text[:2000]
                        except Exception:
                            pass

                    # Debug logging: full request/response
                    if debug_mode:
                        _log_debug(name, payload, response.status_code, resp_body, response.elapsed.total_seconds() * 1000 if hasattr(response, 'elapsed') else 0)

            op_task.__name__ = name
            return op_task

        task_funcs[op_name] = {"func": make_task(op_name, query, variables, delay, op_name), "weight": weight}

    # Error logging
    error_count = [0]
    # Size tracking per operation
    size_stats = {}

    def _track_size(op_name, req_bytes, resp_bytes):
        if op_name not in size_stats:
            size_stats[op_name] = {"total_req": 0, "total_resp": 0, "count": 0}
        size_stats[op_name]["total_req"] += req_bytes
        size_stats[op_name]["total_resp"] += resp_bytes
        size_stats[op_name]["count"] += 1

    def _log_error(op_name, message, status_code):
        if error_count[0] >= 500:
            return
        error_count[0] += 1
        entry = {"timestamp": time.time(), "operation": op_name, "message": message, "status_code": status_code}
        try:
            with open(errors_path, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception:
            pass

    # Debug logging
    debug_count = [0]

    def _log_debug(op_name, request_payload, status_code, response_body, latency_ms):
        if debug_count[0] >= 1000:
            return
        debug_count[0] += 1
        # Redact auth headers
        entry = {
            "timestamp": time.time(),
            "operation": op_name,
            "request": {
                "url": url,
                "method": "POST",
                "body": request_payload,
            },
            "response": {
                "status_code": status_code,
                "body": response_body if isinstance(response_body, (dict, list)) else str(response_body)[:2000] if response_body else None,
                "latency_ms": round(latency_ms, 2),
            },
        }
        try:
            with open(debug_log_path, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception:
            pass

    # Create user class dynamically
    tasks_dict = {}
    for op_name, td in task_funcs.items():
        tasks_dict[td["func"]] = td["weight"]

    UserClass = type("DynamicUser", (HttpUser,), {
        "host": host,
        "wait_time": constant_pacing(1),
        "tasks": tasks_dict,
        "_start_time": time.time(),
    })

    # Setup environment
    env = Environment(user_classes=[UserClass], events=events)
    env.create_local_runner()
    assert env.runner is not None
    runner = env.runner  # non-optional local alias for use in closures

    # Build operation type map
    op_type_map = {op["name"]: op.get("type", "query") for op in operations}

    # Stats writer greenlet
    start_time = time.time()

    def write_stats():
        while True:
            gevent.sleep(2)
            elapsed = time.time() - start_time
            stats_data = {
                "timestamp": time.time(),
                "elapsed_sec": round(elapsed, 1),
                "user_count": runner.user_count,
                "state": runner.state,
                "total_rps": 0,
                "total_requests": 0,
                "total_failures": 0,
                "operations": {},
            }

            for entry in runner.stats.entries.values():
                ss = size_stats.get(entry.name, {"total_req": 0, "total_resp": 0, "count": 0})
                stats_data["operations"][entry.name] = {
                    "operation_type": op_type_map.get(entry.name, "query"),
                    "request_count": entry.num_requests,
                    "failure_count": entry.num_failures,
                    "avg_response_ms": round(entry.avg_response_time, 2) if entry.num_requests else 0,
                    "min_response_ms": round(entry.min_response_time, 2) if entry.min_response_time is not None else 0,
                    "max_response_ms": round(entry.max_response_time, 2) if entry.max_response_time else 0,
                    "p50_response_ms": round(entry.get_response_time_percentile(0.5) or 0, 2),
                    "p90_response_ms": round(entry.get_response_time_percentile(0.9) or 0, 2),
                    "p95_response_ms": round(entry.get_response_time_percentile(0.95) or 0, 2),
                    "p99_response_ms": round(entry.get_response_time_percentile(0.99) or 0, 2),
                    "tps_actual": round(entry.current_rps, 2) if hasattr(entry, 'current_rps') else 0,
                    "total_response_bytes": ss["total_resp"],
                    "total_request_bytes": ss["total_req"],
                    "avg_response_bytes": round(ss["total_resp"] / ss["count"], 0) if ss["count"] > 0 else 0,
                    "avg_request_bytes": round(ss["total_req"] / ss["count"], 0) if ss["count"] > 0 else 0,
                }
                stats_data["total_requests"] += entry.num_requests
                stats_data["total_failures"] += entry.num_failures
                if hasattr(entry, 'current_rps'):
                    stats_data["total_rps"] += entry.current_rps

            stats_data["total_rps"] = round(stats_data["total_rps"], 2)

            # Atomic write
            try:
                tmp = tempfile.NamedTemporaryFile(mode="w", dir=str(run_path), suffix=".tmp", delete=False)
                json.dump(stats_data, tmp)
                tmp.close()
                os.rename(tmp.name, str(stats_path))
            except Exception:
                pass

            # Check stop sentinel
            if stop_path.exists():
                runner.quit()
                break

    stats_greenlet = gevent.spawn(write_stats)

    # Start the run
    runner.start(user_count, spawn_rate=user_count / max(ramp_up, 1))

    # Duration-based stop
    def duration_stop():
        gevent.sleep(duration)
        if not stop_path.exists():
            runner.quit()

    duration_greenlet = gevent.spawn(duration_stop)

    runner.greenlet.join()

    # Write final results
    final = {
        "timestamp": time.time(),
        "elapsed_sec": round(time.time() - start_time, 1),
        "user_count": user_count,
        "operations": {},
    }
    for entry in runner.stats.entries.values():
        ss = size_stats.get(entry.name, {"total_req": 0, "total_resp": 0, "count": 0})
        final["operations"][entry.name] = {
            "operation_type": op_type_map.get(entry.name, "query"),
            "request_count": entry.num_requests,
            "failure_count": entry.num_failures,
            "avg_response_ms": round(entry.avg_response_time, 2) if entry.num_requests else 0,
            "min_response_ms": round(entry.min_response_time, 2) if entry.min_response_time is not None else 0,
            "max_response_ms": round(entry.max_response_time, 2) if entry.max_response_time else 0,
            "p50_response_ms": round(entry.get_response_time_percentile(0.5) or 0, 2),
            "p90_response_ms": round(entry.get_response_time_percentile(0.9) or 0, 2),
            "p95_response_ms": round(entry.get_response_time_percentile(0.95) or 0, 2),
            "p99_response_ms": round(entry.get_response_time_percentile(0.99) or 0, 2),
            "total_response_bytes": ss["total_resp"],
            "total_request_bytes": ss["total_req"],
            "avg_response_bytes": round(ss["total_resp"] / ss["count"], 0) if ss["count"] > 0 else 0,
            "avg_request_bytes": round(ss["total_req"] / ss["count"], 0) if ss["count"] > 0 else 0,
        }

    try:
        with open(done_path, "w") as f:
            json.dump(final, f)
    except Exception:
        pass


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python worker.py <run_dir>")
        sys.exit(1)
    try:
        run_worker(sys.argv[1])
    except Exception:
        traceback.print_exc()
        sys.exit(1)
