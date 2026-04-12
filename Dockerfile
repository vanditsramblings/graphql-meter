# ── Stage 1: k6 binary ──────────────────────────────────────
FROM grafana/k6:0.54.0 AS k6

# ── Stage 2: Build wheels ───────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /tmp
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Stage 3: Runtime ────────────────────────────────────────
FROM python:3.12-slim

# Create non-root user first
RUN useradd --create-home --shell /bin/bash appuser

WORKDIR /app

# Copy k6 binary
COPY --from=k6 /usr/bin/k6 /usr/local/bin/k6

# Copy pre-built dependencies from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages/ /usr/local/lib/python3.12/site-packages/
COPY --from=builder /usr/local/bin/ /usr/local/bin/

# Copy application (excluded files via .dockerignore)
COPY --chown=appuser:appuser backend/ backend/
COPY --chown=appuser:appuser frontend/ frontend/

# Create data directory with proper permissions
RUN mkdir -p backend/data/runs && chown -R appuser:appuser backend/data

USER appuser

# Pre-download vendored frontend libraries (Preact, HTM, fonts) into the image
RUN python -c "import sys; sys.path.insert(0, '.'); from backend.vendor_manager import ensure_vendor_libs; ensure_vendor_libs()"

EXPOSE 8899

CMD ["python", "backend/app.py"]
