#!/bin/bash
set -e

echo "==================================="
echo "  GraphQL Meter — Setup & Start"
echo "==================================="

cd "$(dirname "$0")"

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "[1/5] Creating virtual environment..."
    python3 -m venv .venv
else
    echo "[1/5] Virtual environment exists."
fi

# Activate venv
source .venv/bin/activate
echo "  Using Python: $(python --version)"

# Install dependencies
echo "[2/5] Installing Python dependencies..."
pip install -q -r requirements.txt

# Copy .env if not exists
if [ ! -f ".env" ]; then
    echo "[3/5] Creating .env from .env.example..."
    cp .env.example .env
else
    echo "[3/5] .env already exists."
fi

# Download vendored frontend libs
echo "[4/5] Downloading frontend vendor libraries..."
mkdir -p frontend/vendor
if [ ! -f "frontend/vendor/preact.mjs" ]; then
    curl -sL "https://unpkg.com/preact@10.24.3/dist/preact.mjs" -o frontend/vendor/preact.mjs
    curl -sL "https://unpkg.com/preact@10.24.3/hooks/dist/hooks.mjs" -o frontend/vendor/preact-hooks.mjs
    curl -sL "https://unpkg.com/htm@3.1.1/dist/htm.mjs" -o frontend/vendor/htm.mjs
    echo "  Downloaded: preact.mjs, preact-hooks.mjs, htm.mjs"
else
    echo "  Vendor libraries already present."
fi

# Download k6 binary
echo "[5/5] Checking k6 binary..."
K6_VERSION="v0.54.0"
RAW_OS=$(uname -s | tr '[:upper:]' '[:lower:]')
ARCH=$(uname -m)
case "$ARCH" in
    x86_64) ARCH="amd64" ;;
    aarch64|arm64) ARCH="arm64" ;;
esac

if ! command -v k6 &> /dev/null && [ ! -f ".venv/bin/k6" ]; then
    if [ "$RAW_OS" = "darwin" ]; then
        K6_OS="macos"
        K6_URL="https://github.com/grafana/k6/releases/download/${K6_VERSION}/k6-${K6_VERSION}-${K6_OS}-${ARCH}.zip"
        echo "  Downloading k6 ${K6_VERSION} for ${K6_OS}/${ARCH} (zip)..."
        TMPDIR_K6=$(mktemp -d)
        curl -sL "$K6_URL" -o "${TMPDIR_K6}/k6.zip"
        unzip -qo "${TMPDIR_K6}/k6.zip" -d "${TMPDIR_K6}"
        cp "${TMPDIR_K6}/k6-${K6_VERSION}-${K6_OS}-${ARCH}/k6" .venv/bin/k6
        chmod +x .venv/bin/k6
        rm -rf "${TMPDIR_K6}"
    else
        K6_OS="$RAW_OS"
        K6_URL="https://github.com/grafana/k6/releases/download/${K6_VERSION}/k6-${K6_VERSION}-${K6_OS}-${ARCH}.tar.gz"
        echo "  Downloading k6 ${K6_VERSION} for ${K6_OS}/${ARCH} (tar.gz)..."
        curl -sL "$K6_URL" | tar xz --strip-components=1 -C .venv/bin/ "k6-${K6_VERSION}-${K6_OS}-${ARCH}/k6"
    fi
    echo "  k6 installed at .venv/bin/k6"
else
    echo "  k6 already available."
fi

echo ""
echo "==================================="
echo "  Starting GraphQL Meter on :8899"
echo "==================================="
echo ""

python backend/app.py
