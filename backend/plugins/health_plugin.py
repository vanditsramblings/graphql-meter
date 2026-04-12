"""Health plugin — status, resources (CPU/memory), settings export, runtime config."""

import os
import time
from datetime import datetime, timezone

import psutil
from fastapi import HTTPException, Request
from pydantic import BaseModel
from typing import Optional

from backend.core.plugin_base import PluginBase
from backend.config import get_settings
from backend.plugins.auth_plugin import require_auth, require_role

from backend import __version__ as _VERSION

_start_time = time.time()


class ConfigUpdate(BaseModel):
    max_concurrent_runs: Optional[int] = None
    stats_poll_interval_sec: Optional[int] = None
    max_error_buffer: Optional[int] = None
    max_run_history: Optional[int] = None
    chart_history_runs: Optional[int] = None
    enable_k6: Optional[bool] = None
    enable_locust: Optional[bool] = None
    worker_threads: Optional[int] = None
    dashboard_poll_sec: Optional[int] = None
    running_test_poll_sec: Optional[int] = None
    debug: Optional[bool] = None


class HealthPlugin(PluginBase):
    @property
    def name(self) -> str:
        return "health"

    @property
    def description(self) -> str:
        return "Health check, CPU/memory/threads via psutil, settings export"

    def _register_routes(self):
        @self.router.get("/status")
        async def health_status():
            uptime = time.time() - _start_time
            hours = int(uptime // 3600)
            minutes = int((uptime % 3600) // 60)
            seconds = int(uptime % 60)
            return {
                "status": "ok",
                "uptime": f"{hours}h {minutes}m {seconds}s",
                "uptime_seconds": int(uptime),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "version": _VERSION,
            }

        @self.router.get("/resources")
        async def health_resources():
            process = psutil.Process(os.getpid())
            mem = process.memory_info()
            cpu_percent = psutil.cpu_percent(interval=None)
            virtual_mem = psutil.virtual_memory()
            return {
                "cpu_percent": cpu_percent,
                "cpu_count": psutil.cpu_count(),
                "memory": {
                    "process_rss_mb": round(mem.rss / 1024 / 1024, 1),
                    "process_vms_mb": round(mem.vms / 1024 / 1024, 1),
                    "system_total_mb": round(virtual_mem.total / 1024 / 1024, 1),
                    "system_available_mb": round(virtual_mem.available / 1024 / 1024, 1),
                    "system_percent": virtual_mem.percent,
                },
                "threads": process.num_threads(),
                "pid": os.getpid(),
            }

        @self.router.get("/settings")
        async def health_settings():
            settings = get_settings()
            return {
                "host": settings.HOST,
                "port": settings.PORT,
                "debug": settings.DEBUG,
                "db_path": settings.DB_PATH,
                "max_concurrent_runs": settings.MAX_CONCURRENT_RUNS,
                "stats_poll_interval_sec": settings.STATS_POLL_INTERVAL_SEC,
                "max_error_buffer": settings.MAX_ERROR_BUFFER,
                "max_run_history": settings.MAX_RUN_HISTORY,
                "chart_history_runs": settings.CHART_HISTORY_RUNS,
                "jwt_expiry_hours": settings.JWT_EXPIRY_HOURS,
                "enable_k6": settings.ENABLE_K6,
                "enable_locust": settings.ENABLE_LOCUST,
                "worker_threads": settings.WORKER_THREADS,
                "uvicorn_workers": settings.UVICORN_WORKERS,
                "dashboard_poll_sec": settings.DASHBOARD_POLL_SEC,
                "running_test_poll_sec": settings.RUNNING_TEST_POLL_SEC,
            }

        @self.router.put("/config")
        async def update_config(body: ConfigUpdate, request: Request):
            """Update runtime configuration (admin only). Changes persist until restart."""
            require_role(request, "admin")
            user = require_auth(request)

            import backend.config as cfg_module
            settings = get_settings()
            changes = {}

            for field, value in body.model_dump(exclude_none=True).items():
                attr = field.upper()
                if hasattr(settings, attr):
                    old = getattr(settings, attr)
                    setattr(settings, attr, value)
                    changes[field] = {"old": old, "new": value}

            # Cache the modified settings instance
            cfg_module.get_settings = lambda _s=settings: _s

            return {"updated": changes}

        @self.router.get("/config/validate")
        async def validate_config(request: Request):
            """Dry-run: return current effective config without changing anything."""
            require_auth(request)
            settings = get_settings()
            return {
                "max_concurrent_runs": settings.MAX_CONCURRENT_RUNS,
                "enable_k6": settings.ENABLE_K6,
                "enable_locust": settings.ENABLE_LOCUST,
                "worker_threads": settings.WORKER_THREADS,
                "max_error_buffer": settings.MAX_ERROR_BUFFER,
                "max_run_history": settings.MAX_RUN_HISTORY,
                "chart_history_runs": settings.CHART_HISTORY_RUNS,
                "dashboard_poll_sec": settings.DASHBOARD_POLL_SEC,
                "running_test_poll_sec": settings.RUNNING_TEST_POLL_SEC,
                "debug": settings.DEBUG,
            }
