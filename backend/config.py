"""Pydantic BaseSettings — all configuration from environment variables / .env file."""

from pydantic_settings import BaseSettings
from pydantic import Field
from pathlib import Path
import os


class Settings(BaseSettings):
    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8899
    DEBUG: bool = False

    # Database
    DB_PATH: str = str(Path(__file__).parent / "data" / "portal.db")

    # Auth
    JWT_SECRET: str = "change-me-in-production-use-a-long-random-string"
    JWT_EXPIRY_HOURS: int = 24

    # Load Testing
    MAX_CONCURRENT_RUNS: int = 3
    STATS_POLL_INTERVAL_SEC: int = 2
    MAX_ERROR_BUFFER: int = 500
    MAX_RUN_HISTORY: int = 200
    CHART_HISTORY_RUNS: int = 10

    # Engine toggles
    ENABLE_K6: bool = True
    ENABLE_LOCUST: bool = True

    # Thread / performance tuning
    WORKER_THREADS: int = 4
    UVICORN_WORKERS: int = 1

    # k6
    K6_BINARY_PATH: str = ""

    # Encryption for auth provider secrets
    ENCRYPTION_KEY: str = ""  # Auto-derived from JWT_SECRET if empty

    # Polling intervals (frontend hints)
    DASHBOARD_POLL_SEC: int = 5
    RUNNING_TEST_POLL_SEC: int = 2

    # Azure AD (optional)
    AZURE_TENANT_ID: str = ""
    AZURE_CLIENT_ID: str = ""
    AZURE_CLIENT_SECRET: str = ""
    AZURE_SCOPE: str = ""

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }


def get_settings() -> Settings:
    return Settings()
