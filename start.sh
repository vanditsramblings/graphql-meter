#!/bin/bash
set -e

echo "==================================="
echo "  GraphQL Meter — Setup & Start"
echo "==================================="

cd "$(dirname "$0")"

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "[1/4] Creating virtual environment..."
    python3 -m venv .venv
else
    echo "[1/4] Virtual environment exists."
fi

# Activate venv
source .venv/bin/activate
echo "  Using Python: $(python --version)"

# Install package in editable mode
echo "[2/4] Installing graphql-meter (editable)..."
pip install -q -e ".[dev]"

# Copy .env if not exists
if [ ! -f ".env" ]; then
    echo "[3/4] Creating .env from .env.example..."
    cp .env.example .env
else
    echo "[3/4] .env already exists."
fi

# Provision vendor libs + k6 via Python managers
echo "[4/4] Provisioning vendor libs and k6..."
python -c "
from backend.vendor_manager import ensure_vendor_libs
from backend.k6_manager import ensure_k6
ensure_vendor_libs()
ensure_k6()
"

echo ""
echo "==================================="
echo "  Starting GraphQL Meter on :8899"
echo "==================================="
echo ""

python backend/app.py
