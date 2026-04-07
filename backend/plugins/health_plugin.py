"""Health plugin — status, resources (CPU/memory), settings export."""

import os
import time
from datetime import datetime, timezone

import psutil

from backend.core.plugin_base import PluginBase
from backend.config import get_settings

_start_time = time.time()


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
                "version": "0.1.0",
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
            # Export non-secret settings only
            return {
                "host": settings.HOST,
                "port": settings.PORT,
                "debug": settings.DEBUG,
                "db_path": settings.DB_PATH,
                "max_concurrent_runs": settings.MAX_CONCURRENT_RUNS,
                "stats_poll_interval_sec": settings.STATS_POLL_INTERVAL_SEC,
                "max_error_buffer": settings.MAX_ERROR_BUFFER,
                "max_run_history": settings.MAX_RUN_HISTORY,
                "jwt_expiry_hours": settings.JWT_EXPIRY_HOURS,
            }
