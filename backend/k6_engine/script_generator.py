"""k6 script generator — convert test config to k6 JavaScript test script."""

import json


def generate_script(config: dict) -> str:
    """Generate a k6 test script from config."""
    gp = config.get("global_params", {})
    operations = [o for o in config.get("operations", []) if o.get("enabled", True)]
    host = gp.get("host", "http://localhost:4000")
    graphql_path = gp.get("graphql_path", "/graphql")
    url = f"{host.rstrip('/')}{graphql_path}"
    user_count = gp.get("user_count", 10)
    duration = gp.get("duration_sec", 60)
    ramp_up = gp.get("ramp_up_sec", 10)
    auth_headers = config.get("auth_headers", {})

    # Build scenarios
    scenarios = {}
    total_tps = sum(o.get("tps_percentage", 0) for o in operations)

    for op in operations:
        name = op["name"]
        pct = op.get("tps_percentage", 0)
        vus = max(1, round(user_count * (pct / 100))) if total_tps > 0 else 1
        delay = op.get("delay_start_sec", 0)

        scenarios[name] = {
            "executor": "constant-vus",
            "vus": vus,
            "duration": f"{duration}s",
            "exec": name,
        }
        if delay > 0:
            scenarios[name]["startTime"] = f"{delay}s"

    # Build headers
    base_headers = {"Content-Type": "application/json"}
    base_headers.update(auth_headers)
    headers_json = json.dumps(base_headers)

    # Build script
    lines = [
        'import http from "k6/http";',
        'import { check, sleep } from "k6";',
        'import { Counter, Rate, Trend } from "k6/metrics";',
        '',
        'const errors = new Counter("graphql_errors");',
        'const errorRate = new Rate("graphql_error_rate");',
        '',
        f'const URL = "{url}";',
        f'const HEADERS = {headers_json};',
        '',
        'export const options = {',
        f'  scenarios: {json.dumps(scenarios, indent=4)},',
        '  thresholds: {',
        '    http_req_duration: ["p(95)<2000"],',
        '    graphql_error_rate: ["rate<0.1"],',
        '  },',
        '};',
        '',
    ]

    # Check if any operation has dict variables with {r} — need _resolve helper
    needs_resolve = any(
        isinstance(v.get("value", v.get("default_value", "")), dict) and "{r}" in json.dumps(v.get("value", v.get("default_value", "")))
        for op in operations for v in op.get("variables", [])
    )

    if needs_resolve:
        lines.extend([
            '// Resolve {r} placeholders in nested objects with type coercion',
            'function _resolve(obj, rVal) {',
            '  if (typeof obj === "string") {',
            '    if (obj.indexOf("{r}") === -1) return obj;',
            '    const s = obj.replace(/\\{r\\}/g, rVal);',
            '    const i = parseInt(s, 10);',
            '    if (String(i) === s) return i;',
            '    const f = parseFloat(s);',
            '    if (!isNaN(f) && s.indexOf(".") !== -1) return f;',
            '    return s;',
            '  }',
            '  if (Array.isArray(obj)) return obj.map(v => _resolve(v, rVal));',
            '  if (obj && typeof obj === "object") {',
            '    const out = {};',
            '    for (const [k, v] of Object.entries(obj)) out[k] = _resolve(v, rVal);',
            '    return out;',
            '  }',
            '  return obj;',
            '}',
            '',
        ])

    # Generate exec functions
    for op in operations:
        name = op["name"]
        query = op.get("query", "").replace("\n", "\\n").replace('"', '\\"')
        variables = {}
        for v in op.get("variables", []):
            variables[v["name"]] = v.get("value", v.get("default_value", ""))

        rstart = op.get("data_range_start", 1)
        rend = op.get("data_range_end", 100)

        lines.extend([
            f'export function {name}() {{',
            f'  const rVal = (__ITER % {rend - rstart + 1}) + {rstart};',
        ])

        # Resolve variables
        vars_lines = []
        for k, v in variables.items():
            if isinstance(v, str) and "{r}" in v:
                replaced_expr = v.replace("{r}", "${rVal}")
                # Check if the value resolves to a pure number pattern
                stripped = v.replace("{r}", "1")
                try:
                    int(stripped)
                    # Pure integer pattern like "{r}" or "10{r}"
                    vars_lines.append(f'    "{k}": parseInt(`{replaced_expr}`, 10)')
                    continue
                except ValueError:
                    pass
                try:
                    float(stripped)
                    if "." in stripped:
                        # Float pattern like "{r}.5" or "{r}.99"
                        vars_lines.append(f'    "{k}": parseFloat(`{replaced_expr}`)')
                        continue
                except ValueError:
                    pass
                # String with placeholder
                vars_lines.append(f'    "{k}": `{replaced_expr}`')
            elif isinstance(v, str):
                vars_lines.append(f'    "{k}": "{v}"')
            elif isinstance(v, dict):
                v_str = json.dumps(v)
                if "{r}" in v_str:
                    # Build object with typed resolution
                    vars_lines.append(f'    "{k}": _resolve({json.dumps(v)}, rVal)')
                else:
                    vars_lines.append(f'    "{k}": {json.dumps(v)}')
            else:
                vars_lines.append(f'    "{k}": {json.dumps(v)}')

        lines.append(f'  const variables = {{')
        lines.append(",\n".join(vars_lines))
        lines.append('  };')

        lines.extend([
            f'  const payload = JSON.stringify({{ query: "{query}", variables: variables }});',
            '  const res = http.post(URL, payload, { headers: HEADERS, tags: { name: "' + name + '" } });',
            '  const success = check(res, {',
            '    "status is 200": (r) => r.status === 200,',
            '    "no GraphQL errors": (r) => {',
            '      try { const b = JSON.parse(r.body); return !b.errors; } catch { return true; }',
            '    },',
            '  });',
            '  if (!success) {',
            '    errors.add(1);',
            '    errorRate.add(1);',
            '  } else {',
            '    errorRate.add(0);',
            '  }',
            '}',
            '',
        ])

    # handleSummary
    lines.extend([
        'export function handleSummary(data) {',
        '  return {',
        '    stdout: JSON.stringify(data, null, 2),',
        '  };',
        '}',
    ])

    return "\n".join(lines)
