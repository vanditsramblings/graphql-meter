/**
 * Trends.js — View p50/p90/p95/p99 latency trends across runs for a given config.
 */
import { h } from 'preact';
import { useState, useEffect } from 'preact/hooks';
import htm from 'htm';
import { apiGet } from '../lib/api.js';
import { useToast } from '../components/Toast.js';
import { Spinner } from '../components/Spinner.js';
import { LineChart } from '../components/LineChart.js';
import { Icon } from '../components/Icons.js';

const html = htm.bind(h);

const COLORS = ['var(--chart-1)', 'var(--chart-2)', 'var(--chart-3)', 'var(--chart-5)'];

function fmtMs(n) { return n == null ? '—' : n >= 1000 ? (n / 1000).toFixed(2) + 's' : n.toFixed(0) + 'ms'; }

/** Extract aggregate metrics from a trends entry (summary + operations). */
function extractMetrics(entry) {
    const ops = entry.operations || [];
    const summary = entry.summary || {};
    // Compute averages from per-operation data
    const avg = (field) => {
        const vals = ops.map(o => o[field]).filter(v => v != null && v > 0);
        return vals.length > 0 ? vals.reduce((s, v) => s + v, 0) / vals.length : null;
    };
    const sum = (field) => ops.reduce((s, o) => s + (o[field] || 0), 0);
    return {
        run_id: entry.run_id,
        name: entry.name,
        started_at: entry.started_at,
        p50: avg('p50_response_ms'),
        p90: avg('p90_response_ms'),
        p95: avg('p95_response_ms'),
        p99: avg('p99_response_ms'),
        avg_ms: avg('avg_response_ms'),
        avg_rps: ops.reduce((s, o) => s + (o.tps_actual || 0), 0),
        requests: sum('request_count'),
        errors: sum('failure_count'),
        user_count: summary.user_count,
    };
}

export function Trends() {
    const toast = useToast();
    const [configs, setConfigs] = useState([]);
    const [selectedConfig, setSelectedConfig] = useState('');
    const [trendRows, setTrendRows] = useState([]);
    const [loading, setLoading] = useState(false);
    const [loadingConfigs, setLoadingConfigs] = useState(true);

    useEffect(() => {
        apiGet('/api/testconfig/list').then(res => {
            setConfigs(res?.configs || []);
            setLoadingConfigs(false);
        }).catch(() => setLoadingConfigs(false));
    }, []);

    useEffect(() => {
        if (selectedConfig) fetchTrends();
        else setTrendRows([]);
    }, [selectedConfig]);

    const fetchTrends = async () => {
        setLoading(true);
        try {
            const res = await apiGet('/api/results/trends/' + encodeURIComponent(selectedConfig));
            const entries = (res?.trends || []).map(extractMetrics);
            setTrendRows(entries);
        } catch (e) {
            toast.error(e.message || 'Failed to load trends');
        } finally {
            setLoading(false);
        }
    };

    // Build chart data from trend rows
    const buildChartData = () => {
        if (trendRows.length === 0) return null;
        const labels = trendRows.map((r, i) => '#' + (i + 1));
        const series = [
            { name: 'P50', color: COLORS[0], data: trendRows.map(r => r.p50 ?? 0) },
            { name: 'P90', color: COLORS[1], data: trendRows.map(r => r.p90 ?? 0) },
            { name: 'P95', color: COLORS[2], data: trendRows.map(r => r.p95 ?? 0) },
            { name: 'P99', color: COLORS[3], data: trendRows.map(r => r.p99 ?? 0) },
        ];
        return { labels, series };
    };

    const chartData = buildChartData();

    return html`
        <div>
            <div class="page-header">
                <div>
                    <h1 class="page-title">Performance Trends</h1>
                    <p class="page-subtitle">Latency percentiles across completed runs</p>
                </div>
            </div>

            <div class="card" style="margin-bottom: var(--space-4);">
                <div class="form-group" style="margin-bottom: 0;">
                    <label class="form-label">Configuration</label>
                    ${loadingConfigs ? html`<${Spinner} size="sm" />` : html`
                        <select class="form-select" value=${selectedConfig}
                            onChange=${(e) => setSelectedConfig(e.target.value)}>
                            <option value="">Select configuration...</option>
                            ${configs.map(c => html`
                                <option key=${c.id} value=${c.id}>${c.name}</option>
                            `)}
                        </select>
                    `}
                </div>
            </div>

            ${loading && html`<${Spinner} message="Loading trends..." />`}

            ${!loading && selectedConfig && trendRows.length === 0 && html`
                <div class="card">
                    <div class="empty-state">
                        <div class="empty-state-icon"><${Icon} name="trending-up" size=${32} /></div>
                        <div class="empty-state-title">No data yet</div>
                        <div class="empty-state-description">Run some tests with this config to see trends.</div>
                    </div>
                </div>
            `}

            ${!loading && trendRows.length > 0 && html`
                <div>
                    ${chartData && html`
                        <div class="card" style="margin-bottom: var(--space-4);">
                            <h3 style="margin-bottom: var(--space-3); font-size: var(--font-size-sm);">Latency Over Runs (ms)</h3>
                            <${LineChart}
                                labels=${chartData.labels}
                                series=${chartData.series}
                                height=${300}
                                yLabel="ms"
                            />
                        </div>
                    `}

                    <div class="card">
                        <h3 style="margin-bottom: var(--space-3); font-size: var(--font-size-sm);">Run Details</h3>
                        <div class="table-container">
                            <table class="table">
                                <thead>
                                    <tr>
                                        <th>#</th>
                                        <th>Date</th>
                                        <th style="text-align: right;">Requests</th>
                                        <th style="text-align: right;">Avg (ms)</th>
                                        <th style="text-align: right;">P50</th>
                                        <th style="text-align: right;">P90</th>
                                        <th style="text-align: right;">P95</th>
                                        <th style="text-align: right;">P99</th>
                                        <th style="text-align: right;">RPS</th>
                                        <th style="text-align: right;">Errors</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${trendRows.map((r, i) => html`
                                        <tr key=${r.run_id || i}>
                                            <td>${i + 1}</td>
                                            <td style="white-space: nowrap;">${r.started_at ? (() => { const d = new Date(r.started_at); const dd = String(d.getDate()).padStart(2, '0'); const mm = String(d.getMonth() + 1).padStart(2, '0'); const hh = String(d.getHours()).padStart(2, '0'); const mi = String(d.getMinutes()).padStart(2, '0'); return dd + '/' + mm + ' ' + hh + ':' + mi; })() : '—'}</td>
                                            <td style="text-align: right; font-family: var(--font-mono);">${r.requests ?? '—'}</td>
                                            <td style="text-align: right; font-family: var(--font-mono);">${fmtMs(r.avg_ms)}</td>
                                            <td style="text-align: right; font-family: var(--font-mono);">${fmtMs(r.p50)}</td>
                                            <td style="text-align: right; font-family: var(--font-mono);">${fmtMs(r.p90)}</td>
                                            <td style="text-align: right; font-family: var(--font-mono);">${fmtMs(r.p95)}</td>
                                            <td style="text-align: right; font-family: var(--font-mono);">${fmtMs(r.p99)}</td>
                                            <td style="text-align: right; font-family: var(--font-mono);">${r.avg_rps?.toFixed(1) ?? '—'}</td>
                                            <td style="text-align: right; font-family: var(--font-mono); ${(r.errors || 0) > 0 ? 'color: var(--color-error);' : ''}">${r.errors ?? 0}</td>
                                        </tr>
                                    `)}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            `}
        </div>
    `;
}
