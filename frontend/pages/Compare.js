/**
 * Compare.js — Side-by-side comparison of two test runs.
 * Includes date-range, text search, engine, and status filters to find runs.
 */
import { h } from 'preact';
import { useState, useEffect, useMemo } from 'preact/hooks';
import htm from 'htm';
import { apiGet } from '../lib/api.js';
import { useToast } from '../components/Toast.js';
import { useRoute } from '../lib/router.js';
import { Spinner } from '../components/Spinner.js';
import { LineChart } from '../components/LineChart.js';
import { Icon } from '../components/Icons.js';

const html = htm.bind(h);

function fmtMs(n) { return n == null ? '—' : n >= 1000 ? (n / 1000).toFixed(2) + 's' : n.toFixed(0) + 'ms'; }
function fmtNum(n) { return n == null ? '—' : n.toLocaleString(); }
function fmtDate(iso) { if (!iso) return ''; const d = new Date(iso); return d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'}); }
function toISODate(d) { return d ? d.toISOString().slice(0, 10) : ''; }

function DeltaCell({ v1, v2, lowerIsBetter = true }) {
    if (v1 == null || v2 == null) return html`<td style="text-align: right;">—</td>`;
    const delta = v2 - v1;
    const pct = v1 !== 0 ? ((delta / v1) * 100).toFixed(1) : '—';
    const improved = lowerIsBetter ? delta < 0 : delta > 0;
    const color = delta === 0 ? '' : improved ? 'var(--color-success)' : 'var(--color-error)';
    const iconName = delta === 0 ? null : delta > 0 ? 'trending-up' : 'trending-down';
    return html`<td style="text-align: right; color: ${color}; font-weight: 500;">
        ${iconName && html`<${Icon} name=${iconName} size=${12} style=${{marginRight: '2px'}} />`} ${Math.abs(delta).toFixed(1)} (${pct}%)
    </td>`;
}

/** Filterable run picker with date range, text search, engine & status filters */
function RunPicker({ label, runs, value, onChange, excludeId }) {
    const [search, setSearch] = useState('');
    const [dateFrom, setDateFrom] = useState('');
    const [dateTo, setDateTo] = useState('');
    const [engineFilter, setEngineFilter] = useState('');
    const [statusFilter, setStatusFilter] = useState('');
    const [expanded, setExpanded] = useState(false);

    const filtered = useMemo(() => {
        return runs.filter(r => {
            if (excludeId && r.id === excludeId) return false;
            if (search) {
                const q = search.toLowerCase();
                const name = (r.config_name || r.id || '').toLowerCase();
                const user = (r.created_by || '').toLowerCase();
                if (!name.includes(q) && !user.includes(q) && !r.id.toLowerCase().includes(q)) return false;
            }
            if (engineFilter && (r.engine || 'locust') !== engineFilter) return false;
            if (statusFilter && r.status !== statusFilter) return false;
            if (dateFrom) {
                const d = new Date(r.started_at);
                if (d < new Date(dateFrom + 'T00:00:00')) return false;
            }
            if (dateTo) {
                const d = new Date(r.started_at);
                if (d > new Date(dateTo + 'T23:59:59')) return false;
            }
            return true;
        });
    }, [runs, search, dateFrom, dateTo, engineFilter, statusFilter, excludeId]);

    const selectedRun = runs.find(r => r.id === value);

    return html`
        <div class="form-group">
            <label class="form-label">${label}</label>
            <!-- Selected run display -->
            <div style="display: flex; gap: var(--space-2); margin-bottom: var(--space-2);">
                <div style="flex: 1; padding: var(--space-2) var(--space-3); background: var(--bg-tertiary); border: 1px solid var(--border-medium); border-radius: var(--radius-sm); font-size: var(--font-size-sm); color: ${selectedRun ? 'var(--text-primary)' : 'var(--text-disabled)'}; cursor: pointer; min-height: 34px; display: flex; align-items: center;"
                    onClick=${() => setExpanded(!expanded)}>
                    ${selectedRun ? html`
                        <span style="font-weight: 500;">${selectedRun.config_name || selectedRun.id}</span>
                        <span class="text-muted" style="margin-left: var(--space-2); font-size: var(--font-size-xs);">${fmtDate(selectedRun.started_at)} · ${selectedRun.engine || 'locust'}</span>
                    ` : 'Click to select a run...'}
                    <${Icon} name=${expanded ? 'chevron-up' : 'chevron-down'} size=${14} style=${{marginLeft: 'auto', opacity: 0.5}} />
                </div>
                ${value && html`
                    <button class="btn btn-ghost btn-sm" onClick=${() => { onChange(''); setExpanded(false); }}
                        title="Clear selection"><${Icon} name="x" size=${14} /></button>
                `}
            </div>

            <!-- Expandable filter panel -->
            ${expanded && html`
                <div style="border: 1px solid var(--border-medium); border-radius: var(--radius-md); padding: var(--space-3); background: var(--bg-secondary); margin-bottom: var(--space-2);">
                    <!-- Filter controls -->
                    <div style="display: flex; gap: var(--space-2); margin-bottom: var(--space-3); flex-wrap: wrap;">
                        <input class="form-input" placeholder="Search by name, user, or ID..."
                            value=${search} onInput=${(e) => setSearch(e.target.value)}
                            style="flex: 2; min-width: 160px; font-size: var(--font-size-xs);" />
                        <input class="form-input" type="date" value=${dateFrom}
                            onInput=${(e) => setDateFrom(e.target.value)}
                            style="width: 130px; font-size: var(--font-size-xs);" title="From date" />
                        <input class="form-input" type="date" value=${dateTo}
                            onInput=${(e) => setDateTo(e.target.value)}
                            style="width: 130px; font-size: var(--font-size-xs);" title="To date" />
                        <select class="form-select" value=${engineFilter}
                            onChange=${(e) => setEngineFilter(e.target.value)}
                            style="width: 100px; font-size: var(--font-size-xs);">
                            <option value="">Engine</option>
                            <option value="locust">Locust</option>
                            <option value="k6">k6</option>
                        </select>
                        <select class="form-select" value=${statusFilter}
                            onChange=${(e) => setStatusFilter(e.target.value)}
                            style="width: 110px; font-size: var(--font-size-xs);">
                            <option value="">Status</option>
                            <option value="completed">Completed</option>
                            <option value="failed">Failed</option>
                            <option value="stopped">Stopped</option>
                        </select>
                    </div>
                    <!-- Run list -->
                    <div style="max-height: 240px; overflow-y: auto; border-top: 1px solid var(--border-weak);">
                        ${filtered.length === 0 ? html`
                            <div class="text-muted" style="padding: var(--space-4); text-align: center; font-size: var(--font-size-sm);">
                                No runs match filters${runs.length > 0 ? ' — try adjusting filters' : ''}
                            </div>
                        ` : filtered.map(r => html`
                            <div key=${r.id}
                                style="padding: var(--space-2) var(--space-3); cursor: pointer; border-bottom: 1px solid var(--border-weak); display: flex; align-items: center; gap: var(--space-3); transition: background 100ms ease; ${r.id === value ? 'background: var(--accent-dim);' : ''}"
                                onClick=${() => { onChange(r.id); setExpanded(false); }}
                                onMouseOver=${(e) => { if (r.id !== value) e.currentTarget.style.background = 'var(--bg-hover)'; }}
                                onMouseOut=${(e) => { if (r.id !== value) e.currentTarget.style.background = ''; }}>
                                <div style="flex: 1; min-width: 0;">
                                    <div style="font-weight: 500; font-size: var(--font-size-sm); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
                                        ${r.config_name || r.id}
                                    </div>
                                    <div class="text-muted" style="font-size: var(--font-size-xs);">
                                        ${fmtDate(r.started_at)}${r.created_by ? ' · ' + r.created_by : ''}
                                    </div>
                                </div>
                                <span class="badge badge-${r.status === 'completed' ? 'completed' : r.status === 'failed' ? 'failed' : r.status === 'stopped' ? 'stopped' : 'pending'}" style="font-size: 10px;">
                                    ${r.status}
                                </span>
                                <span class="text-muted" style="font-size: var(--font-size-xs); min-width: 40px; text-align: right;">${r.engine || 'locust'}</span>
                            </div>
                        `)}
                    </div>
                    <div class="text-muted" style="padding-top: var(--space-2); font-size: var(--font-size-xs);">${filtered.length} of ${runs.length} runs</div>
                </div>
            `}
        </div>
    `;
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
        apiGet('/api/results/runs?limit=200').then(res => {
            setRuns(res?.runs || []);
            setLoadingRuns(false);
        }).catch(() => setLoadingRuns(false));
    }, []);

    useEffect(() => {
        if (run1 && run2 && run1 !== run2) {
            fetchComparison();
        } else {
            setComparison(null);
        }
    }, [run1, run2]);

    const fetchComparison = async () => {
        setLoading(true);
        try {
            const res = await apiGet('/api/results/compare?run1=' + encodeURIComponent(run1) + '&run2=' + encodeURIComponent(run2));
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
                    <p class="page-subtitle">Side-by-side run comparison — use filters to find specific runs</p>
                </div>
            </div>

            <div class="card" style="margin-bottom: var(--space-4);">
                ${loadingRuns ? html`<${Spinner} size="sm" />` : html`
                    <div class="form-row">
                        <${RunPicker} label="Baseline (Run 1)" runs=${runs} value=${run1}
                            onChange=${setRun1} excludeId=${run2} />
                        <${RunPicker} label="Comparison (Run 2)" runs=${runs} value=${run2}
                            onChange=${setRun2} excludeId=${run1} />
                    </div>
                `}
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
                                    ${(comparison.summary || []).map(m => {
                                        const isErr = m.metric.toLowerCase().includes('failure');
                                        const isReq = m.metric.toLowerCase().includes('request') && !isErr;
                                        return html`
                                        <tr key=${m.metric}>
                                            <td style="font-weight: 500;">${m.metric}</td>
                                            <td style="text-align: right; font-family: var(--font-mono);">${isErr || isReq ? fmtNum(m.run1) : fmtMs(m.run1)}</td>
                                            <td style="text-align: right; font-family: var(--font-mono);">${isErr || isReq ? fmtNum(m.run2) : fmtMs(m.run2)}</td>
                                            <${DeltaCell} v1=${m.run1} v2=${m.run2} lowerIsBetter=${m.lower_is_better !== false} />
                                        </tr>`;
                                    })}
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
                                            <th style="text-align: right;">R1 Reqs</th>
                                            <th style="text-align: right;">R2 Reqs</th>
                                            <th style="text-align: right;">R1 Avg</th>
                                            <th style="text-align: right;">R2 Avg</th>
                                            <th style="text-align: right;">Avg Delta</th>
                                            <th style="text-align: right;">R1 P95</th>
                                            <th style="text-align: right;">R2 P95</th>
                                            <th style="text-align: right;">P95 Delta</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        ${comparison.operations.map(op => html`
                                            <tr key=${op.name}>
                                                <td style="font-weight: 500;">${op.name}</td>
                                                <td style="text-align: right; font-family: var(--font-mono);">${fmtNum(op.run1_requests)}</td>
                                                <td style="text-align: right; font-family: var(--font-mono);">${fmtNum(op.run2_requests)}</td>
                                                <td style="text-align: right; font-family: var(--font-mono);">${fmtMs(op.run1_avg)}</td>
                                                <td style="text-align: right; font-family: var(--font-mono);">${fmtMs(op.run2_avg)}</td>
                                                <${DeltaCell} v1=${op.run1_avg} v2=${op.run2_avg} />
                                                <td style="text-align: right; font-family: var(--font-mono);">${fmtMs(op.run1_p95)}</td>
                                                <td style="text-align: right; font-family: var(--font-mono);">${fmtMs(op.run2_p95)}</td>
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
