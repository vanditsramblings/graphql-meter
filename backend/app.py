"""GraphQL Meter — FastAPI application entry point."""

import sys
from pathlib import Path

# Ensure backend package is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.config import get_settings
from backend.core.plugin_registry import discover_plugins
from backend.vendor_manager import _find_frontend_dir

settings = get_settings()

from backend import __version__


@asynccontextmanager
async def lifespan(app: FastAPI):
    _seed_default_config()
    yield


app = FastAPI(
    title="GraphQL Meter",
    description="Self-contained GraphQL performance testing platform",
    version=__version__,
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list(),
    allow_credentials=settings.CORS_ORIGINS.strip() != "*",
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure data directory exists
data_dir = Path(settings.DB_PATH).parent
data_dir.mkdir(parents=True, exist_ok=True)
(data_dir / "runs").mkdir(exist_ok=True)

# Load plugins
plugins = discover_plugins()
for name, plugin in plugins.items():
    app.include_router(plugin.router, prefix=f"/api/{name}", tags=[name])


def _seed_default_config():
    """Auto-seed the Self Load Test config if no test configs exist."""
    import json
    import uuid
    from datetime import datetime, timezone

    from backend.plugins.graphql_health_plugin import HEALTH_SCHEMA
    from backend.plugins.storage_plugin import get_db

    db = get_db()
    count = db.execute("SELECT COUNT(*) as cnt FROM test_configs").fetchone()["cnt"]
    if count > 0:
        return

    config_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    operations = [
        {"name": "health", "type": "query",
         "query": "query health { health { status uptime_seconds request_count maintenance_mode timestamp } }",
         "enabled": True, "tps_percentage": 30, "delay_start_sec": 0, "data_range_start": 1, "data_range_end": 100, "variables": []},
        {"name": "serviceInfo", "type": "query",
         "query": "query serviceInfo { serviceInfo { name version environment features } }",
         "enabled": True, "tps_percentage": 20, "delay_start_sec": 0, "data_range_start": 1, "data_range_end": 100, "variables": []},
        {"name": "echo", "type": "query",
         "query": "query echo($message: String!, $messageInteger: Int, $messageDouble: Float, $messageUUID: ID, $messageTime: String) { echo(message: $message, messageInteger: $messageInteger, messageDouble: $messageDouble, messageUUID: $messageUUID, messageTime: $messageTime) { message messageInteger messageDouble messageUUID messageTime received_at request_number } }",
         "enabled": True, "tps_percentage": 25, "delay_start_sec": 0, "data_range_start": 1, "data_range_end": 100,
         "variables": [
             {"name": "message", "type": "String!", "value": "test-{r}", "required": True},
             {"name": "messageInteger", "type": "Int", "value": "{r}", "required": False},
             {"name": "messageDouble", "type": "Float", "value": "{r}.5", "required": False},
             {"name": "messageUUID", "type": "ID", "value": "uuid-{r}", "required": False},
             {"name": "messageTime", "type": "String", "value": "2026-01-01T00:{r}:00Z", "required": False},
         ]},
        {"name": "submitTestData", "type": "mutation",
         "query": "mutation submitTestData($input: TestDataInput!) { submitTestData(input: $input) { id label count score referenceId scheduledAt active processed_at } }",
         "enabled": True, "tps_percentage": 25, "delay_start_sec": 0, "data_range_start": 1, "data_range_end": 100,
         "variables": [
             {"name": "input", "type": "TestDataInput!", "value": {"label": "item-{r}", "count": "{r}", "score": "{r}.99", "referenceId": "ref-{r}", "scheduledAt": "2026-01-01T{r}:00:00Z", "active": True}, "required": True},
         ]},
    ]
    config_json = json.dumps({
        "global_params": {"name": "Self Load Test", "description": "Built-in load test targeting the GraphQL health endpoint (self-test)",
                          "host": "http://localhost:8899", "graphql_path": "/api/graphql-health/graphql",
                          "user_count": 5, "ramp_up_sec": 5, "duration_sec": 30},
        "operations": operations, "engine": "locust", "debug_mode": False, "cleanup_on_stop": False, "auth_provider_id": "",
    })
    db.execute(
        "INSERT INTO test_configs (id, name, description, schema_text, config_json, created_by, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
        (config_id, "Self Load Test", "Built-in load test targeting the GraphQL health endpoint (self-test)",
         HEALTH_SCHEMA, config_json, "system", now, now),
    )
    db.commit()


# Serve frontend static files
frontend_dir = _find_frontend_dir()
if frontend_dir is not None:
    _fd: Path = frontend_dir  # local alias so closures below have a narrowed Path type
    # Serve vendor files
    vendor_dir = _fd / "vendor"
    if vendor_dir.exists():
        app.mount("/vendor", StaticFiles(directory=str(vendor_dir)), name="vendor")

    # Serve frontend static assets (CSS, JS, etc.)
    app.mount("/lib", StaticFiles(directory=str(_fd / "lib")), name="lib")
    app.mount("/components", StaticFiles(directory=str(_fd / "components")), name="components")
    app.mount("/pages", StaticFiles(directory=str(_fd / "pages")), name="pages")

    # Serve app.js and styles.css from frontend root
    @app.get("/app.js")
    async def serve_app_js():
        return FileResponse(str(_fd / "app.js"), media_type="application/javascript")

    @app.get("/favicon.svg")
    async def serve_favicon():
        return FileResponse(str(_fd / "favicon.svg"), media_type="image/svg+xml")

    @app.get("/styles.css")
    async def serve_styles_css():
        return FileResponse(str(_fd / "styles.css"), media_type="text/css")

    # SPA fallback — serve index.html for all non-API, non-static routes
    @app.get("/")
    async def serve_index():
        return FileResponse(str(_fd / "index.html"))

    @app.get("/{path:path}")
    async def serve_spa(path: str):
        # Don't intercept API routes or static files
        if path.startswith("api/") or path.startswith("vendor/"):
            return None
        file_path = _fd / path
        if file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(_fd / "index.html"))


if __name__ == "__main__":
    print(f"\n  GraphQL Meter starting on http://{settings.HOST}:{settings.PORT}\n")
    uvicorn.run(
        app,
        host=settings.HOST,
        port=settings.PORT,
        log_level="info",
    )
