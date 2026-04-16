"""Helpers for exporting the FastAPI OpenAPI schema."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.app import app


def generate_openapi_spec() -> dict[str, Any]:
    """Return the application's OpenAPI schema."""
    return app.openapi()


def export_openapi_spec(output_path: str | Path) -> Path:
    """Write the OpenAPI schema to disk and return the output path."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(generate_openapi_spec(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path
