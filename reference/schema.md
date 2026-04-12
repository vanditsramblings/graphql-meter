# Database Schema Reference

GraphQL Meter uses SQLite (WAL mode) with thread-local connections. Foreign keys are enforced (`PRAGMA foreign_keys=ON`).

## Tables

### metadata

Key-value store for application state.

| Column       | Type | Constraints   | Description                |
|--------------|------|---------------|----------------------------|
| `key`        | TEXT | PRIMARY KEY   | Setting/state name         |
| `value`      | TEXT |               | Setting/state value        |
| `updated_at` | TEXT |               | ISO 8601 last-modified     |

### test_configs

Saved load test configurations (operations, thresholds, parameters).

| Column        | Type | Constraints    | Description                        |
|---------------|------|----------------|------------------------------------|
| `id`          | TEXT | PRIMARY KEY    | UUID                               |
| `name`        | TEXT | NOT NULL       | Display name                       |
| `description` | TEXT |                | Free-text description              |
| `schema_text` | TEXT |                | GraphQL SDL for introspection      |
| `config_json` | TEXT |                | Full config: operations, params    |
| `created_by`  | TEXT |                | Username who created               |
| `created_at`  | TEXT |                | ISO 8601                           |
| `updated_at`  | TEXT |                | ISO 8601                           |

### test_runs

Individual load-test executions linked to a config.

| Column             | Type    | Constraints                                                            | Description                           |
|--------------------|---------|------------------------------------------------------------------------|---------------------------------------|
| `id`               | TEXT    | PRIMARY KEY                                                            | UUID                                  |
| `config_id`        | TEXT    | REFERENCES test_configs(id)                                            | Nullable — set to NULL on config delete |
| `name`             | TEXT    |                                                                        | Run label                             |
| `status`           | TEXT    | CHECK(status IN ('pending','running','completed','failed','stopped'))   | Current lifecycle state               |
| `started_at`       | TEXT    |                                                                        | ISO 8601                              |
| `completed_at`     | TEXT    |                                                                        | ISO 8601                              |
| `user_count`       | INTEGER |                                                                        | Virtual users                         |
| `ramp_up_sec`      | INTEGER |                                                                        | Ramp-up duration in seconds           |
| `duration_sec`     | INTEGER |                                                                        | Total test duration in seconds        |
| `host`             | TEXT    |                                                                        | Target host URL                       |
| `platform`         | TEXT    |                                                                        | Target platform identifier            |
| `config_snapshot`  | TEXT    |                                                                        | Full config JSON at time of run       |
| `summary_json`     | TEXT    |                                                                        | Aggregated results after completion   |
| `error_log`        | TEXT    |                                                                        | Captured error output                 |
| `engine`           | TEXT    |                                                                        | `locust` or `k6`                      |
| `debug_mode`       | INTEGER | DEFAULT 0                                                              | 1 = verbose logging                   |
| `cleanup_on_stop`  | INTEGER | DEFAULT 0                                                              | 1 = run cleanup ops after stopping    |
| `notes`            | TEXT    |                                                                        | User notes                            |
| `tags`             | TEXT    |                                                                        | Comma-separated tags                  |
| `environment_id`   | TEXT    |                                                                        | Linked environment                    |
| `created_by`       | TEXT    |                                                                        | Username who started                  |
| `chart_snapshots`  | TEXT    |                                                                        | JSON array of time-series chart data  |

### operation_results

Per-operation metrics from a completed test run.

| Column                 | Type    | Constraints                | Description                     |
|------------------------|---------|----------------------------|---------------------------------|
| `id`                   | INTEGER | PRIMARY KEY AUTOINCREMENT  | Auto-incrementing ID            |
| `run_id`               | TEXT    | REFERENCES test_runs(id)   | Parent test run                 |
| `operation_name`       | TEXT    |                            | GraphQL operation name          |
| `operation_type`       | TEXT    |                            | `query` or `mutation`           |
| `request_count`        | INTEGER |                            | Total requests sent             |
| `failure_count`        | INTEGER |                            | Failed requests                 |
| `avg_response_ms`      | REAL    |                            | Average response time           |
| `min_response_ms`      | REAL    |                            | Min response time               |
| `max_response_ms`      | REAL    |                            | Max response time               |
| `p50_response_ms`      | REAL    |                            | 50th percentile (median)        |
| `p90_response_ms`      | REAL    |                            | 90th percentile                 |
| `p95_response_ms`      | REAL    |                            | 95th percentile                 |
| `p99_response_ms`      | REAL    |                            | 99th percentile                 |
| `tps_actual`           | REAL    |                            | Achieved transactions/sec       |
| `tps_target`           | REAL    |                            | Target transactions/sec         |
| `total_response_bytes` | INTEGER | DEFAULT 0                  | Total response payload size     |
| `total_request_bytes`  | INTEGER | DEFAULT 0                  | Total request payload size      |
| `avg_response_bytes`   | REAL    | DEFAULT 0                  | Average response payload        |
| `avg_request_bytes`    | REAL    | DEFAULT 0                  | Average request payload         |
| `stats_json`           | TEXT    |                            | Engine-specific raw stats       |

### cleanup_jobs

Cleanup mutation jobs triggered after test completion.

| Column          | Type    | Constraints                                              | Description                    |
|-----------------|---------|----------------------------------------------------------|--------------------------------|
| `id`            | TEXT    | PRIMARY KEY                                              | UUID                           |
| `run_id`        | TEXT    |                                                          | Associated test run            |
| `status`        | TEXT    | CHECK(status IN ('pending','running','completed','failed')) | Job state                    |
| `total_ops`     | INTEGER |                                                          | Total cleanup operations       |
| `completed_ops` | INTEGER | DEFAULT 0                                                | Successfully completed count   |
| `failed_ops`    | INTEGER | DEFAULT 0                                                | Failed operations count        |
| `error_details` | TEXT    |                                                          | Error info if failed           |
| `created_at`    | TEXT    |                                                          | ISO 8601                       |
| `completed_at`  | TEXT    |                                                          | ISO 8601                       |

### environments

Target environment configurations (hosts, TLS, auth links).

| Column                     | Type    | Constraints                                           | Description                           |
|----------------------------|---------|-------------------------------------------------------|---------------------------------------|
| `id`                       | TEXT    | PRIMARY KEY                                           | UUID                                  |
| `name`                     | TEXT    | NOT NULL                                              | Display name                          |
| `platform`                 | TEXT    |                                                       | Platform identifier                   |
| `base_url`                 | TEXT    |                                                       | Base URL (host + port)                |
| `graphql_path`             | TEXT    | DEFAULT '/graphql'                                    | GraphQL endpoint path                 |
| `protocol`                 | TEXT    | DEFAULT 'https', CHECK IN ('http','https','mtls')     | Connection protocol                   |
| `tls_mode`                 | TEXT    | DEFAULT 'standard', CHECK IN ('none','standard','mtls') | TLS mode                           |
| `cert_type`                | TEXT    | DEFAULT '', CHECK IN ('','none','pem','pfx','cert_key') | Certificate format                 |
| `cert_data`                | TEXT    | DEFAULT ''                                            | Client certificate (base64)           |
| `key_data`                 | TEXT    | DEFAULT ''                                            | Private key (base64)                  |
| `cert_password_encrypted`  | TEXT    | DEFAULT ''                                            | Fernet-encrypted cert password        |
| `ca_cert_data`             | TEXT    | DEFAULT ''                                            | CA certificate (base64)               |
| `verify_ssl`               | INTEGER | DEFAULT 1                                             | 1 = verify server cert                |
| `headers_json`             | TEXT    | DEFAULT '{}'                                          | Default headers as JSON object        |
| `auth_provider_id`         | TEXT    | DEFAULT ''                                            | Linked auth provider                  |
| `cert_path`                | TEXT    |                                                       | File path to cert (legacy)            |
| `key_path`                 | TEXT    |                                                       | File path to key (legacy)             |
| `notes`                    | TEXT    |                                                       | Free-text notes                       |
| `created_at`               | TEXT    |                                                       | ISO 8601                              |
| `updated_at`               | TEXT    |                                                       | ISO 8601                              |

### auth_providers

Authentication provider configurations (tokens, OAuth2, etc.). Credentials stored Fernet-encrypted.

| Column             | Type | Constraints                                                                                  | Description                     |
|--------------------|------|----------------------------------------------------------------------------------------------|---------------------------------|
| `id`               | TEXT | PRIMARY KEY                                                                                  | UUID                            |
| `name`             | TEXT | NOT NULL                                                                                     | Display name                    |
| `auth_type`        | TEXT | NOT NULL, CHECK IN ('bearer_token','basic','api_key','oauth2_client_credentials','oauth2_password','jwt_custom') | Auth mechanism type |
| `config_encrypted` | TEXT | NOT NULL                                                                                     | Fernet-encrypted config JSON    |
| `description`      | TEXT |                                                                                              | Free-text description           |
| `created_by`       | TEXT |                                                                                              | Username who created            |
| `created_at`       | TEXT |                                                                                              | ISO 8601                        |
| `updated_at`       | TEXT |                                                                                              | ISO 8601                        |

### graphql_requests

Saved GraphQL queries/mutations in the built-in client.

| Column              | Type | Constraints   | Description                          |
|---------------------|------|---------------|--------------------------------------|
| `id`                | TEXT | PRIMARY KEY   | UUID                                 |
| `name`              | TEXT | NOT NULL      | Request display name                 |
| `description`       | TEXT | DEFAULT ''    | Free-text description                |
| `folder_name`       | TEXT | DEFAULT ''    | Nested folder path (`/`-separated)   |
| `environment_id`    | TEXT | DEFAULT ''    | Linked environment                   |
| `auth_provider_id`  | TEXT | DEFAULT ''    | Linked auth provider                 |
| `query`             | TEXT | NOT NULL      | GraphQL query/mutation text          |
| `variables_json`    | TEXT | DEFAULT '{}'  | Variables as JSON string             |
| `headers_json`      | TEXT | DEFAULT '{}'  | Custom headers as JSON string        |
| `config_id`         | TEXT | DEFAULT ''    | Source test config (if imported)      |
| `operation_name`    | TEXT | DEFAULT ''    | GraphQL operation name               |
| `last_response_json`| TEXT | DEFAULT ''    | Cached last response                 |
| `created_by`        | TEXT |               | Username who created                 |
| `created_at`        | TEXT |               | ISO 8601                             |
| `updated_at`        | TEXT |               | ISO 8601                             |

### graphql_folders

Explicit folder tree for organizing GraphQL client requests.

| Column       | Type | Constraints       | Description                        |
|--------------|------|-------------------|------------------------------------|
| `id`         | TEXT | PRIMARY KEY       | UUID                               |
| `path`       | TEXT | NOT NULL, UNIQUE  | Nested path (`/`-separated, e.g. `Auth/OAuth2`) |
| `created_by` | TEXT |                   | Username who created               |
| `created_at` | TEXT |                   | ISO 8601                           |

## Relationships

```
test_configs  1──*  test_runs      (via config_id, nullable FK)
test_runs     1──*  operation_results  (via run_id FK)
```

- Deleting a test config sets `test_runs.config_id = NULL` (application-level cascade).
- Deleting a folder cascades to all sub-folders and contained requests (application-level, via path prefix matching).
- `environments` and `auth_providers` are referenced by ID strings but not enforced via FK constraints.

## Conventions

- All IDs are `uuid4()` strings.
- All timestamps are ISO 8601 UTC (`datetime.now(timezone.utc).isoformat()`).
- JSON columns store serialized dicts/arrays as TEXT.
- Sensitive fields (`config_encrypted`, `cert_password_encrypted`) use Fernet AES-128-CBC encryption.
- Thread-local connections via `threading.local()` — never share connections across threads.
- WAL mode enabled for concurrent read throughput.
