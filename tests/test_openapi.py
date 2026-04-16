"""Tests for OpenAPI spec export."""

import json

from backend.openapi import export_openapi_spec


def test_export_openapi_spec_writes_json(tmp_path):
    output_path = tmp_path / "openapi.json"

    export_openapi_spec(output_path)

    data = json.loads(output_path.read_text())
    assert data["info"]["title"] == "GraphQL Meter"
    assert data["info"]["version"]
    assert "/api/health/status" in data["paths"]
