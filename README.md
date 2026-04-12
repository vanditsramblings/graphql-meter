# GraphQL Meter

### Schema-driven GraphQL performance testing, without the infrastructure overhead.

[![CI](https://github.com/vanditsramblings/graphql-meter/actions/workflows/ci.yml/badge.svg)](https://github.com/vanditsramblings/graphql-meter/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/docker-ghcr.io-blue.svg)](https://github.com/vanditsramblings/graphql-meter/pkgs/container/graphql-meter)

[Getting Started](#getting-started) |
[Features](#features) |
[Installation](#installation) |
[Configuration](#configuration) |
[Usage](#usage) |
[Architecture](#architecture) |
[Credits](#credits)

---

## What is GraphQL Meter?

GraphQL Meter is a self-hosted platform that transforms your GraphQL schema into fully configured performance tests. Paste a schema, select operations, set traffic distribution, and start load testing -- all from a single web interface. No YAML files, no test scripts to write, no external infrastructure to manage.

It ships as a **single container** with everything included: two load-testing engines (Locust and k6), a real-time dashboard, run history, trend analysis, and a built-in GraphQL client for pre-test verification.

**The problem it solves:** Load testing GraphQL APIs typically requires writing custom scripts, managing test data, configuring authentication, and stitching together multiple tools. GraphQL Meter eliminates this setup cost by auto-discovering operations from your schema and generating everything needed to run, monitor, and compare tests.

<!-- TODO: Add hero screenshot of the dashboard -->
<!-- ![Dashboard](docs/screenshots/dashboard.png) -->

---

## Features

### Schema-Driven Test Generation
Paste a GraphQL schema and GraphQL Meter will parse it (via AST with regex fallback), discover all queries and mutations, and generate type-aware test variables with smart defaults. No hand-authored test scripts required.

<!-- TODO: Screenshot of schema parsing step -->
<!-- ![Schema Parsing](docs/screenshots/schema-parse.png) -->

### Dual Engine Support
Choose between **Locust** (Python, greenlet-based) and **k6** (Go binary, scenarios-based) per test run. Both engines are subprocess-isolated from the main server -- they never share the FastAPI process. Compare results across engines to validate findings.

### Real-Time Monitoring
Watch throughput, response times (p50/p90/p95/p99), error rates, and per-operation breakdowns update live every 2 seconds. Interactive SVG charts with multi-series support render directly in the browser with no chart library dependency.

<!-- TODO: Screenshot of live test monitoring -->
<!-- ![Live Monitoring](docs/screenshots/live-test.png) -->

### Test Configuration Wizard
A 3-step wizard guides test setup: define global parameters, select operations with TPS percentage distribution (must sum to 100%), and review before starting. Saved configurations are reusable across runs.

### Run Comparison and Trend Analysis
Compare any two runs side-by-side with delta highlighting (green = improved, red = regressed). View latency and throughput trends over the last N runs for any test configuration to catch regressions early.

<!-- TODO: Screenshot of comparison view -->
<!-- ![Compare](docs/screenshots/compare.png) -->

### Environment Profiles
Define multiple target environments with distinct base URLs, TLS/mTLS settings, client certificates (PEM, PFX, cert+key), custom headers, and linked authentication providers. Switch between dev, staging, and production targets without reconfiguring tests.

### Encrypted Authentication
Six auth provider types: Bearer Token, Basic Auth, API Key, OAuth2 Client Credentials, OAuth2 Password, and Custom JWT. All secrets encrypted at rest with Fernet AES. Thread-safe token caching with automatic refresh for OAuth2 flows.

### Built-In GraphQL Client
Verify queries against your target API before running load tests. Split-pane editor with variables/headers panels, environment and auth provider resolution, saved requests, and import from test configurations.

### Runtime Configuration
Adjust concurrency limits, enable/disable engines, toggle debug mode, and tune polling intervals from the Settings page without restarting the server. All changes take effect immediately for the current session.

### Dark Professional UI
Grafana/k6-inspired dark theme with CSS custom properties. No build step -- Preact + HTM served as vendored ES modules. Every page handles loading, empty, and error states.

---

## Getting Started

The fastest path to a running instance:

```bash
# Docker (recommended)
docker run -p 8899:8899 ghcr.io/vanditsramblings/graphql-meter:latest

# Then open http://localhost:8899
# Login: admin / admin123
```

GraphQL Meter is ready at **http://localhost:8899** with both engines enabled, k6 pre-installed, and default credentials.

---

## Installation

### Docker (recommended)

Includes Python runtime, Locust, k6, and all frontend assets. Nothing else to install.

```bash
# Run with default settings
docker run -p 8899:8899 ghcr.io/vanditsramblings/graphql-meter:latest

# Run with custom configuration
docker run -p 8899:8899 \
  -e JWT_SECRET=your-secret-key-here \
  -e MAX_CONCURRENT_RUNS=5 \
  -e ENABLE_K6=true \
  -e ENABLE_LOCUST=true \
  -v graphql-meter-data:/app/backend/data \
  ghcr.io/vanditsramblings/graphql-meter:latest

# Run with persistent data
docker run -p 8899:8899 \
  -v $(pwd)/data:/app/backend/data \
  ghcr.io/vanditsramblings/graphql-meter:latest

# Run with limited resources (recommended for shared/CI environments)
docker run -p 8899:8899 \
  --memory=512m \
  --cpus=1.0 \
  -e MAX_CONCURRENT_RUNS=1 \
  -v graphql-meter-data:/app/backend/data \
  ghcr.io/vanditsramblings/graphql-meter:latest
```

### Python / pipx

Requires Python 3.11 or later. k6 is auto-downloaded on first use.

```bash
# Install globally via pipx (recommended for CLI tools)
pipx install graphql-meter
graphql-meter

# Or install in a virtual environment
pip install graphql-meter
graphql-meter
```

### From Source (for development)

```bash
git clone https://github.com/vanditsramblings/graphql-meter.git
cd graphql-meter
./start.sh
```

### Kubernetes (Helm)

A Helm chart is provided in the `helm/` directory for deploying to Kubernetes clusters.

```bash
# Install with default settings
helm install graphql-meter ./helm/graphql-meter

# Install with custom values
helm install graphql-meter ./helm/graphql-meter \
  --set env.JWT_SECRET=my-production-secret \
  --set persistence.size=5Gi \
  --set resources.limits.memory=2Gi

# Install with ingress enabled
helm install graphql-meter ./helm/graphql-meter \
  --set ingress.enabled=true \
  --set ingress.hosts[0].host=graphql-meter.example.com \
  --set ingress.hosts[0].paths[0].path=/ \
  --set ingress.hosts[0].paths[0].pathType=Prefix

# Upgrade an existing release
helm upgrade graphql-meter ./helm/graphql-meter

# Uninstall
helm uninstall graphql-meter
```

The chart includes:
- **Deployment** with configurable resource limits, liveness/readiness probes
- **Service** (ClusterIP by default, configurable)
- **PersistentVolumeClaim** for SQLite data and run artifacts (2Gi default)
- **Ingress** (optional, disabled by default)

See [`helm/graphql-meter/values.yaml`](helm/graphql-meter/values.yaml) for all configurable values.

`start.sh` performs the following steps:
1. Creates a Python virtual environment (`.venv`)
2. Installs the package in editable mode with dev dependencies
3. Copies `.env.example` to `.env` if not present
4. Downloads vendored frontend libraries (Preact, HTM)
5. Downloads the k6 binary for your platform
6. Starts the server on **http://localhost:8899**

**Manual setup** (if you prefer not to use `start.sh`):

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env        # Edit settings as needed
python backend/app.py        # Or: graphql-meter
```

### Verifying the Installation

After starting, confirm the server is running:

```bash
curl http://localhost:8899/api/health/status
# {"status":"ok","uptime":"0h 0m 5s",...}
```

Default login credentials:

| Username | Password | Role |
|:---|:---|:---|
| `admin` | `admin123` | Full access |
| `maintainer` | `maintainer123` | Create, run, configure |
| `reader` | `reader123` | View and run tests |

---

## Configuration

All settings are controlled via environment variables or a `.env` file. Copy `.env.example` and modify as needed.

### Server

| Variable | Default | Description |
|:---|:---|:---|
| `HOST` | `0.0.0.0` | Bind address |
| `PORT` | `8899` | Listen port |
| `DEBUG` | `false` | Enable debug logging |

### Authentication

| Variable | Default | Description |
|:---|:---|:---|
| `JWT_SECRET` | (change me) | Secret key for JWT HS256 signing. **Must be changed in production.** |
| `JWT_EXPIRY_HOURS` | `24` | Token expiration time |
| `ENCRYPTION_KEY` | (auto) | Fernet key for encrypting auth provider secrets. Auto-derived from `JWT_SECRET` if empty. |

### Load Testing

| Variable | Default | Description |
|:---|:---|:---|
| `MAX_CONCURRENT_RUNS` | `3` | Maximum simultaneous test runs |
| `STATS_POLL_INTERVAL_SEC` | `2` | How often engines write stats (seconds) |
| `MAX_ERROR_BUFFER` | `500` | Maximum error lines kept in memory per run |
| `MAX_RUN_HISTORY` | `200` | Maximum runs retained in history |
| `CHART_HISTORY_RUNS` | `10` | Runs with full chart data retained |

### Engine Toggles

| Variable | Default | Description |
|:---|:---|:---|
| `ENABLE_K6` | `true` | Enable the k6 load testing engine |
| `ENABLE_LOCUST` | `true` | Enable the Locust load testing engine |
| `K6_BINARY_PATH` | (auto) | Path to k6 binary. Auto-detected/downloaded if empty. |

### Performance Tuning

| Variable | Default | Description |
|:---|:---|:---|
| `WORKER_THREADS` | `4` | Background worker thread count |
| `UVICORN_WORKERS` | `1` | Uvicorn process workers |
| `DASHBOARD_POLL_SEC` | `5` | Dashboard refresh interval (frontend hint) |
| `RUNNING_TEST_POLL_SEC` | `2` | Live test page refresh interval (frontend hint) |

### Database

| Variable | Default | Description |
|:---|:---|:---|
| `DB_PATH` | `backend/data/portal.db` | SQLite database file path |

### Overriding Configuration

**Environment variables** (highest priority):
```bash
export JWT_SECRET=my-production-secret
export MAX_CONCURRENT_RUNS=5
graphql-meter
```

**Docker environment**:
```bash
docker run -e JWT_SECRET=my-secret -e ENABLE_K6=false -p 8899:8899 ghcr.io/vanditsramblings/graphql-meter
```

**.env file** (loaded automatically from working directory):
```ini
MAX_CONCURRENT_RUNS=5
ENABLE_K6=true
ENABLE_LOCUST=true
```

**Runtime overrides** (admin only, via UI Settings page or API):
```bash
curl -X PUT http://localhost:8899/api/health/config \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"max_concurrent_runs": 5, "enable_k6": false}'
```

Runtime changes persist until the server is restarted.

---

## Usage

### 1. Define a Test Configuration

Navigate to **Test Configs** and use the 3-step wizard:

1. **Global Parameters**: Name your test, set target host, user count, ramp-up period, and duration. Paste your GraphQL schema.
2. **Operations**: Select which queries/mutations to include. Set TPS percentage for each (must total 100%). Configure test data and delay start times.
3. **Review**: Choose engine (Locust or k6), enable debug mode or cleanup-on-stop, then save or start immediately.

### 2. Run a Test

From the Test History page, start any saved configuration. The live monitoring view shows:
- Real-time throughput and response time charts
- Per-operation stats table (requests, failures, latency percentiles)
- Scrollable error log
- Stop button with confirmation

### 3. Analyze Results

- **Test History**: Browse completed, failed, and running tests with sortable tables
- **Compare**: Select two runs for side-by-side delta analysis
- **Trends**: View latency and RPS over the last N runs for any configuration
- **Export**: Download self-contained HTML reports for any run

### 4. Manage Environments

Create environment profiles with TLS/mTLS settings, client certificates, custom headers, and linked auth providers. Switch between environments when starting tests.

---

## Architecture

```
graphql-meter/
+-- backend/
|   +-- app.py                    # FastAPI entry, CORS, plugin loading, static files
|   +-- config.py                 # Pydantic BaseSettings (.env)
|   +-- cli.py                    # CLI entry point (graphql-meter command)
|   +-- k6_manager.py             # k6 binary auto-detection / download
|   +-- vendor_manager.py         # Frontend vendor library provisioning
|   +-- core/                     # Plugin base, registry, cache
|   +-- plugins/                  # 12 auto-discovered plugins
|   +-- models/                   # Pydantic models
|   +-- locust_engine/            # Locust subprocess: worker, token manager
|   +-- k6_engine/                # k6 subprocess: script generator, metrics parser
|   +-- data/                     # SQLite DB + per-run IPC directories
+-- frontend/
|   +-- index.html                # Importmap, ES modules entry
|   +-- app.js                    # Root: Auth -> Router -> Layout -> Pages
|   +-- styles.css                # Dark theme, CSS custom properties
|   +-- lib/                      # API client, auth context, router, feature flags
|   +-- components/               # 15+ reusable components (charts, tables, modals)
|   +-- pages/                    # 11 route pages
|   +-- vendor/                   # Vendored Preact, HTM (.mjs)
+-- tests/                        # 126+ pytest unit tests
```

| Component | Technology | Notes |
|:---|:---|:---|
| Backend | Python 3.12+ / FastAPI / Uvicorn | Plugin-based, async |
| Database | SQLite (WAL mode) | Thread-local connections |
| Frontend | Preact 10 + HTM 3 | No build step, ES modules |
| Load Engine | Locust + k6 | Subprocess-isolated |
| Auth | Manual JWT HS256 | 3 roles, 12 feature flags |
| Encryption | Fernet AES-128-CBC | PBKDF2-SHA256 key derivation |

---

## Dependencies

### Runtime

| Package | Version | Purpose |
|:---|:---|:---|
| [FastAPI](https://fastapi.tiangolo.com/) | >=0.115.0 | Web framework and REST API |
| [Uvicorn](https://www.uvicorn.org/) | >=0.32.0 | ASGI server |
| [Pydantic](https://docs.pydantic.dev/) | >=2.10.0 | Data validation, settings |
| [Locust](https://locust.io/) | >=2.32.0 | Python-based load testing engine |
| [graphql-core](https://github.com/graphql-python/graphql-core) | >=3.2.5 | GraphQL schema parsing |
| [httpx](https://www.python-httpx.org/) | >=0.28.0 | HTTP client for GraphQL client |
| [cryptography](https://cryptography.io/) | >=44.0.0 | Fernet encryption for secrets |
| [psutil](https://github.com/giampaolo/psutil) | >=6.1.0 | System resource monitoring |
| [requests](https://requests.readthedocs.io/) | >=2.32.0 | HTTP client for auth flows |
| [PyYAML](https://pyyaml.org/) | >=6.0.2 | Configuration parsing |
| [cachetools](https://github.com/tkem/cachetools) | >=5.5.0 | TTL cache for tokens |

### External Binaries

| Binary | Version | Required | Notes |
|:---|:---|:---|:---|
| [k6](https://grafana.com/docs/k6/) | v0.54.0 | Optional | Auto-downloaded on first use. Set `K6_BINARY_PATH` for custom location. Disable with `ENABLE_K6=false`. |

### Frontend (vendored, no build step)

| Library | Version | Purpose |
|:---|:---|:---|
| [Preact](https://preactjs.com/) | 10.24.3 | UI framework (3KB alternative to React) |
| [HTM](https://github.com/developit/htm) | 3.1.1 | Tagged template JSX alternative |

### Development

| Package | Version | Purpose |
|:---|:---|:---|
| [pytest](https://docs.pytest.org/) | >=8.0 | Test framework |
| [httpx](https://www.python-httpx.org/) | >=0.28.0 | Test HTTP client |

---

## Running Tests

```bash
source .venv/bin/activate
python -m pytest tests/ -q --tb=short
```

126+ tests cover storage, auth, environments, auth providers, GraphQL client, and test config CRUD with full RBAC validation.

---

## Credits

GraphQL Meter is built on the shoulders of these open-source projects:

- **[Locust](https://locust.io/)** -- Scalable Python load testing framework by the Locust community
- **[k6](https://k6.io/)** -- Modern load testing tool by Grafana Labs
- **[FastAPI](https://fastapi.tiangolo.com/)** -- High-performance Python web framework by Sebastian Ramirez
- **[Preact](https://preactjs.com/)** -- Fast 3kB React alternative by Jason Miller
- **[HTM](https://github.com/developit/htm)** -- JSX-like syntax in tagged templates by Jason Miller
- **[graphql-core](https://github.com/graphql-python/graphql-core)** -- GraphQL implementation for Python
- **[SQLite](https://sqlite.org/)** -- The most widely deployed database engine

UI design inspired by [Grafana](https://grafana.com/) and [k6 Studio](https://github.com/grafana/k6-studio) dark themes.

---

## License

Apache 2.0 -- see [LICENSE](LICENSE).

---

## Support

- **Issues**: [GitHub Issues](https://github.com/vanditsramblings/graphql-meter/issues)
- **Discussions**: [GitHub Discussions](https://github.com/vanditsramblings/graphql-meter/discussions)