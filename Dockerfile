# ── Stage 1: k6 binary ──────────────────────────────────────
FROM grafana/k6:0.54.0 AS k6

# ── Stage 2: Python runtime ─────────────────────────────────
FROM python:3.12-slim AS runtime

WORKDIR /app

# Install k6 from official image
COPY --from=k6 /usr/bin/k6 /usr/local/bin/k6

# Install Python dependencies (layer cached unless requirements change)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY backend/ backend/
COPY frontend/ frontend/

# Create data directory
RUN mkdir -p backend/data/runs

# Non-root user for security
RUN useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8899

CMD ["python", "backend/app.py"]
