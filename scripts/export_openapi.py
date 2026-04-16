#!/usr/bin/env python3
"""Export the FastAPI OpenAPI schema to a JSON file."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.openapi import export_openapi_spec


def main() -> None:
    output_path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "reference" / "openapi.json"
    written = export_openapi_spec(output_path)
    print(f"OpenAPI spec written to {written}")


if __name__ == "__main__":
    main()
