"""GraphQL Meter — FastAPI application entry point."""

import os
import sys
from pathlib import Path

# Ensure backend package is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn

from backend.config import get_settings
from backend.core.plugin_registry import discover_plugins

settings = get_settings()

app = FastAPI(
    title="GraphQL Meter",
    description="Self-contained GraphQL performance testing platform",
    version="0.1.0",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
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

# Serve frontend static files
frontend_dir = Path(__file__).parent.parent / "frontend"
if frontend_dir.exists():
    # Serve vendor files
    vendor_dir = frontend_dir / "vendor"
    if vendor_dir.exists():
        app.mount("/vendor", StaticFiles(directory=str(vendor_dir)), name="vendor")

    # Serve frontend static assets (CSS, JS, etc.)
    app.mount("/lib", StaticFiles(directory=str(frontend_dir / "lib")), name="lib")
    app.mount("/components", StaticFiles(directory=str(frontend_dir / "components")), name="components")
    app.mount("/pages", StaticFiles(directory=str(frontend_dir / "pages")), name="pages")

    # Serve app.js and styles.css from frontend root
    @app.get("/app.js")
    async def serve_app_js():
        return FileResponse(str(frontend_dir / "app.js"), media_type="application/javascript")

    @app.get("/styles.css")
    async def serve_styles_css():
        return FileResponse(str(frontend_dir / "styles.css"), media_type="text/css")

    # SPA fallback — serve index.html for all non-API, non-static routes
    @app.get("/")
    async def serve_index():
        return FileResponse(str(frontend_dir / "index.html"))

    @app.get("/{path:path}")
    async def serve_spa(path: str):
        # Don't intercept API routes or static files
        if path.startswith("api/") or path.startswith("vendor/"):
            return None
        file_path = frontend_dir / path
        if file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(frontend_dir / "index.html"))


if __name__ == "__main__":
    print(f"\n  GraphQL Meter starting on http://{settings.HOST}:{settings.PORT}\n")
    uvicorn.run(
        app,
        host=settings.HOST,
        port=settings.PORT,
        log_level="info",
    )
