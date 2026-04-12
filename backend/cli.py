"""CLI entry point for graphql-meter."""

import sys


def main():
    """Start the GraphQL Meter server."""
    from backend.vendor_manager import ensure_vendor_libs
    from backend.config import get_settings

    ensure_vendor_libs()

    import uvicorn
    from backend.app import app

    settings = get_settings()
    print(f"\n  GraphQL Meter starting on http://{settings.HOST}:{settings.PORT}\n")
    uvicorn.run(app, host=settings.HOST, port=settings.PORT, log_level="info")


if __name__ == "__main__":
    main()
