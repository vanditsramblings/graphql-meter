/**
 * Compare.js — Side-by-side comparison of two test runs.
 */
import { h } from 'preact';
import { useState, useEffect } from 'preact/hooks';
import htm from 'htm';
import { apiGet } from '../lib/api.js';
import { useToast } from '../components/Toast.js';
import { useRoute } from '../lib/router.js';
import { Spinner } from '../components/Spinner.js';
import { LineChart } from '../components/LineChart.js';

const html = htm.bind(h);

function fmtMs(n) { return n == null ? '—' : n >= 1000 ? (n / 1000).toFixed(2) + 's' : n.toFixed(0) + 'ms'; }
function fmtNum(n) { return n == null ? '—' : n.toLocaleString(); }

function DeltaCell({ v1, v2, lowerIsBetter = true }) {
    if (v1 == null || v2 == null) return html`<td style="text-align: right;">—</td>`;
    const delta = v2 - v1;
    const pct = v1 !== 0 ? ((delta / v1) * 100).toFixed(1) : '—';
    const improved = lowerIsBetter ? delta < 0 : delta > 0;
    const color = delta === 0 ? '' : improved ? 'var(--color-success)' : 'var(--color-error)';
    const arrow = delta === 0 ? '' : delta > 0 ? '▲' : '▼';
    return html`<td style="text-align: right; color: ${color}; font-weight: 500;">
        ${arrow} ${Math.abs(delta).toFixed(1)} (${pct}%)
    </td>`;
}

export function Compare() {
    const { params } = useRoute();
    const toast = useToast();
    const [runs, setRuns] = useState([]);
    const [run1, setRun1] = useState(params?.run1 || '');
    const [run2, setRun2] = useState(params?.run2 || '');
    const [comparison, setComparison] = useState(null);
    const [loading, setLoading] = useState(false);
    const [loadingRuns, setLoadingRuns] = useState(true);

    useEffect(() => {
        apiGet('/api/results/runs').then(res => {
            setRuns(res?.runs || []);
            setLoadingRuns(false);
        }).catch(() => setLoadingRuns(false));
    }, []);

    useEffect(() => {
        if (run1 && run2 && run1 !== run2) {
            fetchComparison();
        }
    }, [run1, run2]);

    const fetchComparison = async () => {
        setLoading(true);
        try {
            const res = await apiGet(`/api/results/compare?run1=${encodeURIComponent(run1)}&run2=${encodeURIComponent(run2)}`);
            setComparison(res);
        } catch (e) {
            toast.error(e.message || 'Compare failed');
        } finally {
            setLoading(false);
        }
    };

    return html`
        <div>
            <div class="page-header">
                <div>
                    <h1 class="page-title">Compare Runs</h1>
                    <p class="page-subtitle">Side-by-side run comparison</p>
                </div>
            </div>

            <div class="card" style="margin-bottom: var(--space-4);">
                <div class="form-row">
                    <div class="form-group">
                        <label class="form-label">Baseline (Run 1)</label>
                        ${loadingRuns ? html`<${Spinner} size="sm" />` : html`
                            <select class="form-select" value=${run1} onChange=${(e) => setRun1(e.target.value)}>
                                <option value="">Select run...</option>
                                ${runs.map(r => html`
                                    <option key=${r.id} value=${r.id}>
                                        ${r.config_name || r.id} — ${new Date(r.started_at).toLocaleDateString()} (${r.engine || 'locust'})
                                    </option>
                                `)}
                            </select>
                        `}
                    </div>
                    <div class="form-group">
                        <label class="form-label">Comparison (Run 2)</label>
                        <select class="form-select" value=${run2} onChange=${(e) => setRun2(e.target.value)}>
                            <option value="">Select run...</option>
                            ${runs.map(r => html`
                                <option key=${r.id} value=${r.id}>
                                    ${r.config_name || r.id} — ${new Date(r.started_at).toLocaleDateString()} (${r.engine || 'locust'})
                                </option>
                            `)}
                        </select>
                    </div>
                </div>
            </div>

            ${loading && html`<${Spinner} message="Comparing..." />`}

            ${comparison && !loading && html`
                <div>
                    <!-- Summary delta -->
                    <div class="card" style="margin-bottom: var(--space-4);">
                        <h3 style="margin-bottom: var(--space-3); font-size: var(--font-size-sm);">Overall Delta</h3>
                        <div class="table-container">
                            <table class="table">
                                <thead>
                                    <tr>
                                        <th>Metric</th>
                                        <th style="text-align: right;">Run 1</th>
                                        <th style="text-align: right;">Run 2</th>
                                        <th style="text-align: right;">Delta</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${(comparison.summary || []).map(m => html`
                                        <tr key=${m.metric}>
                                            <td>${m.metric}</td>
                                            <td style="text-align: right;">${fmtMs(m.run1)}</td>
                                            <td style="text-align: right;">${fmtMs(m.run2)}</td>
                                            <${DeltaCell} v1=${m.run1} v2=${m.run2} lowerIsBetter=${m.lower_is_better !== false} />
                                        </tr>
                                    `)}
                                </tbody>
                            </table>
                        </div>
                    </div>

                    <!-- Per-operation comparison -->
                    ${(comparison.operations || []).length > 0 && html`
                        <div class="card">
                            <h3 style="margin-bottom: var(--space-3); font-size: var(--font-size-sm);">Per-Operation</h3>
                            <div class="table-container">
                                <table class="table">
                                    <thead>
                                        <tr>
                                            <th>Operation</th>
                                            <th style="text-align: right;">Run 1 Avg</th>
                                            <th style="text-align: right;">Run 2 Avg</th>
                                            <th style="text-align: right;">Delta</th>
                                            <th style="text-align: right;">Run 1 P95</th>
                                            <th style="text-align: right;">Run 2 P95</th>
                                            <th style="text-align: right;">Delta</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        ${comparison.operations.map(op => html`
                                            <tr key=${op.name}>
                                                <td style="font-weight: 500;">${op.name}</td>
                                                <td style="text-align: right;">${fmtMs(op.run1_avg)}</td>
                                                <td style="text-align: right;">${fmtMs(op.run2_avg)}</td>
                                                <${DeltaCell} v1=${op.run1_avg} v2=${op.run2_avg} />
                                                <td style="text-align: right;">${fmtMs(op.run1_p95)}</td>
                                                <td style="text-align: right;">${fmtMs(op.run2_p95)}</td>
                                                <${DeltaCell} v1=${op.run1_p95} v2=${op.run2_p95} />
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
