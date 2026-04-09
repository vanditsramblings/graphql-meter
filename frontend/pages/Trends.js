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

const html = htm.bind(h);

const COLORS = ['var(--color-primary)', 'var(--color-warning)', 'var(--color-error)', '#9c27b0'];

export function Trends() {
    const toast = useToast();
    const [configs, setConfigs] = useState([]);
    const [selectedConfig, setSelectedConfig] = useState('');
    const [trends, setTrends] = useState(null);
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
    }, [selectedConfig]);

    const fetchTrends = async () => {
        setLoading(true);
        try {
            const res = await apiGet(`/api/results/trends/${encodeURIComponent(selectedConfig)}`);
            setTrends(res);
        } catch (e) {
            toast.error(e.message || 'Failed to load trends');
        } finally {
            setLoading(false);
        }
    };

    // Transform trends data for LineChart
    const buildChartData = () => {
        if (!trends?.runs || trends.runs.length === 0) return null;

        const labels = trends.runs.map((r, i) => `#${i + 1}`);
        const series = [
            { name: 'P50', color: COLORS[0], data: trends.runs.map(r => r.p50 ?? 0) },
            { name: 'P90', color: COLORS[1], data: trends.runs.map(r => r.p90 ?? 0) },
            { name: 'P95', color: COLORS[2], data: trends.runs.map(r => r.p95 ?? 0) },
            { name: 'P99', color: COLORS[3], data: trends.runs.map(r => r.p99 ?? 0) },
        ];
        return { labels, series };
    };

    const chartData = buildChartData();

    return html`
        <div>
            <div class="page-header">
                <div>
                    <h1 class="page-title">Performance Trends</h1>
                    <p class="page-subtitle">Latency percentiles across runs</p>
                </div>
            </div>

            <div class="card" style="margin-bottom: var(--space-4);">
                <div class="form-group">
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

            ${!loading && trends && html`
                <div>
                    ${chartData ? html`
                        <div class="card" style="margin-bottom: var(--space-4);">
                            <h3 style="margin-bottom: var(--space-3); font-size: var(--font-size-sm);">Latency Over Runs (ms)</h3>
                            <${LineChart}
                                labels=${chartData.labels}
                                series=${chartData.series}
                                height=${300}
                                yLabel="ms"
                            />
                        </div>
                    ` : html`
                        <div class="card">
                            <div class="empty-state">
                                <div class="empty-state-icon">📈</div>
                                <div class="empty-state-title">No data yet</div>
                                <div class="empty-state-description">Run some tests with this config to see trends.</div>
                            </div>
                        </div>
                    `}

                    ${trends.runs && trends.runs.length > 0 && html`
                        <div class="card">
                            <h3 style="margin-bottom: var(--space-3); font-size: var(--font-size-sm);">Run Details</h3>
                            <div class="table-container">
                                <table class="table">
                                    <thead>
                                        <tr>
                                            <th>#</th>
                                            <th>Date</th>
                                            <th>Engine</th>
                                            <th>Users</th>
                                            <th style="text-align: right;">P50</th>
                                            <th style="text-align: right;">P90</th>
                                            <th style="text-align: right;">P95</th>
                                            <th style="text-align: right;">P99</th>
                                            <th style="text-align: right;">Avg RPS</th>
                                            <th style="text-align: right;">Errors</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        ${trends.runs.map((r, i) => html`
                                            <tr key=${r.id || i}>
                                                <td>${i + 1}</td>
                                                <td>${r.started_at ? new Date(r.started_at).toLocaleDateString() : '—'}</td>
                                                <td><span class="badge">${(r.engine || 'locust').toUpperCase()}</span></td>
                                                <td>${r.user_count ?? '—'}</td>
                                                <td style="text-align: right;">${r.p50?.toFixed(0) ?? '—'}</td>
                                                <td style="text-align: right;">${r.p90?.toFixed(0) ?? '—'}</td>
                                                <td style="text-align: right;">${r.p95?.toFixed(0) ?? '—'}</td>
                                                <td style="text-align: right;">${r.p99?.toFixed(0) ?? '—'}</td>
                                                <td style="text-align: right;">${r.avg_rps?.toFixed(1) ?? '—'}</td>
                                                <td style="text-align: right; ${(r.errors || 0) > 0 ? 'color: var(--color-error);' : ''}">${r.errors ?? 0}</td>
                                            </tr>
                                        `)}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    `}
                </div>
            `}
        </div>
    `;
}
