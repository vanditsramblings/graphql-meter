/**
 * TestRun.js — Live monitoring dashboard for an active test run.
 * Polls engine status every 2s and renders charts + stats + error log.
 */
import { h } from 'preact';
import { useState, useEffect, useRef } from 'preact/hooks';
import htm from 'htm';
import { apiGet, apiPost } from '../lib/api.js';
import { useToast } from '../components/Toast.js';
import { navigate, useRoute } from '../lib/router.js';
import { Spinner } from '../components/Spinner.js';
import { StatusBadge } from '../components/StatusBadge.js';
import { LiveChart } from '../components/LiveChart.js';
import { ErrorLog } from '../components/ErrorLog.js';
import { ConfirmDialog } from '../components/ConfirmDialog.js';
import { Icon } from '../components/Icons.js';

const html = htm.bind(h);

function fmtNum(n) { if (n == null) return '—'; return n >= 1000 ? (n / 1000).toFixed(1) + 'k' : n.toFixed(1); }
function fmtMs(n) { if (n == null) return '—'; return n >= 1000 ? (n / 1000).toFixed(2) + 's' : n.toFixed(0) + 'ms'; }
function fmtDur(s) { if (!s) return '00:00'; const m = Math.floor(s / 60); const sec = Math.floor(s % 60); return `${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`; }
function fmtBytes(b) { if (b == null || b === 0) return '—'; if (b < 1024) return b.toFixed(0) + 'B'; if (b < 1048576) return (b / 1024).toFixed(1) + 'KB'; return (b / 1048576).toFixed(1) + 'MB'; }

export function TestRun() {
    const { params } = useRoute();
    const toast = useToast();
    const [status, setStatus] = useState(null);
    const [loading, setLoading] = useState(true);
    const [showStop, setShowStop] = useState(false);
    const [stopping, setStopping] = useState(false);
    const [chartSnapshots, setChartSnapshots] = useState([]);
    const [activeTab, setActiveTab] = useState('stats');
    const [configDuration, setConfigDuration] = useState(0);
    const pollRef = useRef(null);
    const runId = params?.id;
    const engine = params?.engine || 'locust';
    const isK6 = engine === 'k6';

    const fetchStatus = async () => {
        if (!runId) return;
        try {
            const res = await apiGet(`/api/${engine}/status/${runId}`);
            if (res) {
                setStatus(res);

                // Extract configured duration for chart x-axis range
                if (configDuration === 0 && res.started_at) {
                    try {
                        const runMeta = await apiGet('/api/results/runs/' + runId);
                        if (runMeta?.duration_sec) setConfigDuration(runMeta.duration_sec);
                    } catch (e) { /* ignore */ }
                }

                // Chart snapshots come from the API (either engine deque for running or DB for completed)
                if (res.chart_snapshots && res.chart_snapshots.length > 0) {
                    setChartSnapshots(res.chart_snapshots);
                }

                if (res.status === 'completed' || res.status === 'failed' || res.status === 'stopped') {
                    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
                }
            }
        } catch (e) {
            // silent
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        if (!runId) return;
        fetchStatus();
        pollRef.current = setInterval(fetchStatus, 2000);
        return () => { if (pollRef.current) clearInterval(pollRef.current); };
    }, [runId, engine]);

    const handleStop = async () => {
        setStopping(true);
        try {
            await apiPost(`/api/${engine}/stop/${runId}`, {});
            toast.success('Stop signal sent');
            setShowStop(false);
        } catch (e) {
            toast.error(e.message || 'Failed to stop');
        } finally {
            setStopping(false);
        }
    };

    if (!runId) return html`<div class="card"><p class="text-muted">No run ID specified</p></div>`;
    if (loading) return html`<${Spinner} size="lg" message="Connecting to run..." />`;
    if (!status) return html`<div class="card"><p class="text-muted">Run not found</p></div>`;

    const isRunning = status.status === 'running';
    const elapsed = status.started_at ? (Date.now() - new Date(status.started_at).getTime()) / 1000 : 0;
    const totalRequests = (status.operations || []).reduce((s, o) => s + (o.total_requests || 0), 0);
    const totalFailures = (status.operations || []).reduce((s, o) => s + (o.failures || 0), 0);
    const totalRps = (status.operations || []).reduce((s, o) => s + (o.rps || 0), 0);
    const errorRate = totalRequests > 0 ? (totalFailures / totalRequests * 100).toFixed(1) : '0';

    return html`
        <div>
            <div class="page-header">
                <div class="flex items-center gap-3">
                    <button class="btn btn-ghost btn-sm" onClick=${() => navigate('/test-history')}>←</button>
                    <div>
                        <h1 class="page-title">${status.config_name || 'Test Run'}</h1>
                        <p class="page-subtitle">Run ID: ${runId}</p>
                    </div>
                    <${StatusBadge} status=${status.status} />
                </div>
                ${isRunning && html`
                    <button class="btn btn-danger" onClick=${() => setShowStop(true)}>■ Stop Test</button>
                `}
            </div>

            <!-- Summary Cards -->
            <div class="metric-grid" style="margin-bottom: var(--space-4);">
                <div class="metric-card info">
                    <div class="metric-value">${fmtDur(elapsed)}</div>
                    <div class="metric-label">Elapsed</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value">${status.user_count || '—'}</div>
                    <div class="metric-label">Users</div>
                </div>
                <div class="metric-card success">
                    <div class="metric-value">${fmtNum(totalRps)}</div>
                    <div class="metric-label">RPS</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value">${fmtNum(totalRequests)}</div>
                    <div class="metric-label">Total Requests</div>
                </div>
                <div class="metric-card ${totalFailures > 0 ? 'error' : 'success'}">
                    <div class="metric-value">${totalFailures}</div>
                    <div class="metric-label">Failures</div>
                </div>
                <div class="metric-card ${parseFloat(errorRate) > 5 ? 'error' : parseFloat(errorRate) > 1 ? 'warning' : 'success'}">
                    <div class="metric-value">${errorRate}%</div>
                    <div class="metric-label">Error Rate</div>
                </div>
            </div>

            <!-- Error banner for failed runs -->
            ${status.status === 'failed' && (status.errors || []).length > 0 && html`
                <div class="card" style="margin-bottom: var(--space-4); border-left: 4px solid var(--color-error); background: rgba(239,68,68,0.08); padding: var(--space-4);">
                    <h3 style="color: var(--color-error); margin-bottom: var(--space-2); font-size: var(--font-size-base);">Test Failed</h3>
                    <div style="max-height: 200px; overflow-y: auto; font-family: var(--font-mono); font-size: var(--font-size-xs); white-space: pre-wrap; color: var(--text-secondary);">
                        ${(status.errors || []).map(e => typeof e === 'string' ? e : (e.message || JSON.stringify(e))).join('\n')}
                    </div>
                </div>
            `}

            <!-- Charts (full-width, stacked, per-operation lines) -->
            <div style="margin-bottom: var(--space-4);">
                <div class="card" style="margin-bottom: var(--space-3);">
                    <${LiveChart} snapshots=${chartSnapshots} field="op_rps" label="Requests / sec" unit="rps" maxDuration=${configDuration} height=${260} chartId="rps" />
                </div>
                <div class="card">
                    <${LiveChart} snapshots=${chartSnapshots} field="lat" label="Avg Latency" unit="ms" maxDuration=${configDuration} height=${260} chartId="latency" />
                </div>
            </div>

            <!-- Tabbed section: Stats / Errors / Debug Logs -->
            <div class="tabs" style="margin-bottom: var(--space-3);">
                <button class=${`tab ${activeTab === 'stats' ? 'active' : ''}`}
                    onClick=${() => setActiveTab('stats')}>
                    Per-Operation Stats ${(status.operations || []).length > 0 ? '(' + (status.operations || []).length + ')' : ''}
                </button>
                <button class=${`tab ${activeTab === 'errors' ? 'active' : ''}`}
                    onClick=${() => setActiveTab('errors')}>
                    Errors ${(status.errors || []).length > 0 ? '(' + (status.errors || []).length + ')' : ''}
                </button>
                ${status.debug_mode && html`
                    <button class=${`tab ${activeTab === 'debug' ? 'active' : ''}`}
                        onClick=${() => setActiveTab('debug')}>
                        Debug Logs ${isK6 ? '' : (status.debug_logs || []).length > 0 ? '(' + (status.debug_logs || []).length + ')' : ''}
                        ${isK6 && html`<span class="info-tooltip-inline" data-tooltip="Debug logs are not available for k6 engine. k6 runs as a compiled binary and does not expose per-request details.">ⓘ</span>`}
                    </button>
                `}
            </div>

            ${activeTab === 'stats' && html`
                <div class="card" style="margin-bottom: var(--space-4);">
                    ${(status.operations || []).length === 0 ? html`
                        <div class="empty-state" style="padding: var(--space-4);">
                            <div class="text-muted">No operation stats yet. ${isRunning ? 'Waiting for data...' : 'No data recorded for this run.'}</div>
                        </div>
                    ` : html`
                        <div class="table-container">
                            <table class="table">
                                <thead>
                                    <tr>
                                        <th>Operation</th>
                                        <th>Type</th>
                                        <th style="text-align: right;">Requests</th>
                                        <th style="text-align: right;">Failures</th>
                                        <th style="text-align: right;">RPS</th>
                                        <th style="text-align: right;">Avg</th>
                                        <th style="text-align: right;">P50</th>
                                        <th style="text-align: right;">P90</th>
                                        <th style="text-align: right;">P95</th>
                                        <th style="text-align: right;">P99</th>
                                        <th style="text-align: right;">Avg Req</th>
                                        <th style="text-align: right;">Avg Resp</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${(status.operations || []).map(op => {
                                        const failRate = (op.total_requests || 0) > 0 ? (op.failures || 0) / (op.total_requests || 1) * 100 : 0;
                                        return html`
                                        <tr key=${op.name}>
                                            <td style="font-weight: 500;">${op.name}</td>
                                            <td><span class="badge badge-${op.type === 'mutation' ? 'warning' : 'running'}">${op.type || '—'}</span></td>
                                            <td style="text-align: right; font-family: var(--font-mono);">${op.total_requests || 0}</td>
                                            <td style="text-align: right; font-family: var(--font-mono); ${(op.failures || 0) > 0 ? 'color: var(--color-error); font-weight: 600;' : 'color: var(--color-success);'}">${op.failures || 0}${failRate > 0 ? ' (' + failRate.toFixed(1) + '%)' : ''}</td>
                                            <td style="text-align: right; font-family: var(--font-mono);">${fmtNum(op.rps || 0)}</td>
                                            <td style="text-align: right; font-family: var(--font-mono);">${fmtMs(op.avg_response_time)}</td>
                                            <td style="text-align: right; font-family: var(--font-mono);">${fmtMs(op.p50)}</td>
                                            <td style="text-align: right; font-family: var(--font-mono);">${fmtMs(op.p90)}</td>
                                            <td style="text-align: right; font-family: var(--font-mono);">${fmtMs(op.p95)}</td>
                                            <td style="text-align: right; font-family: var(--font-mono);">${fmtMs(op.p99)}</td>
                                            <td style="text-align: right; font-family: var(--font-mono);">${fmtBytes(op.avg_request_bytes)}</td>
                                            <td style="text-align: right; font-family: var(--font-mono);">${fmtBytes(op.avg_response_bytes)}</td>
                                        </tr>`;
                                    })}
                                </tbody>
                            </table>
                        </div>
                    `}
                </div>
            `}

            ${activeTab === 'errors' && html`
                <div class="card" style="margin-bottom: var(--space-4);">
                    ${(status.errors || []).length === 0 ? html`
                        <div class="empty-state" style="padding: var(--space-4);">
                            <div class="text-muted">No errors recorded.</div>
                        </div>
                    ` : html`
                        <${ErrorLog} errors=${status.errors} maxHeight="500px" />
                    `}
                </div>
            `}

            ${activeTab === 'debug' && status.debug_mode && html`
                <div class="card" style="margin-bottom: var(--space-4);">
                    ${isK6 ? html`
                        <div class="empty-state" style="padding: var(--space-4);">
                            <div class="text-muted">
                                <${Icon} name="info" size=${16} style=${{marginRight: '4px', verticalAlign: 'middle'}} />
                                Debug logs are not available for k6 engine. k6 runs as a compiled Go binary and does not expose per-request details like Locust does.
                            </div>
                        </div>
                    ` : html`
                        ${(status.debug_logs || []).length === 0 ? html`
                        <div class="empty-state" style="padding: var(--space-4);">
                            <div class="text-muted">No debug logs yet. ${isRunning ? 'Waiting for requests...' : ''}</div>
                        </div>
                    ` : html`
                        <div style="max-height: 600px; overflow-y: auto;">
                            ${(status.debug_logs || []).map((log, idx) => html`
                                <div key=${idx} style="border-bottom: 1px solid var(--border-primary); padding: var(--space-3); font-size: var(--font-size-xs);">
                                    <div class="flex items-center justify-between" style="margin-bottom: var(--space-2);">
                                        <span style="font-weight: 600; color: var(--text-primary);">${log.operation || '—'}</span>
                                        <div class="flex items-center gap-3">
                                            <span class="badge ${log.response?.status_code === 200 ? 'badge-running' : 'badge-error'}">
                                                ${log.response?.status_code || '—'}
                                            </span>
                                            <span class="text-muted">${log.response?.latency_ms ? log.response.latency_ms.toFixed(0) + 'ms' : '—'}</span>
                                            <span class="text-muted">${log.timestamp ? new Date(log.timestamp * 1000).toLocaleTimeString() : ''}</span>
                                        </div>
                                    </div>
                                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-3);">
                                        <div>
                                            <div class="text-muted" style="margin-bottom: 4px; font-weight: 500;">Request</div>
                                            <pre style="margin: 0; padding: var(--space-2); background: var(--bg-tertiary); border-radius: var(--radius-sm); overflow-x: auto; max-height: 200px; white-space: pre-wrap; word-break: break-all; font-family: var(--font-mono); font-size: 11px;">${JSON.stringify(log.request?.body, null, 2)}</pre>
                                        </div>
                                        <div>
                                            <div class="text-muted" style="margin-bottom: 4px; font-weight: 500;">Response</div>
                                            <pre style="margin: 0; padding: var(--space-2); background: var(--bg-tertiary); border-radius: var(--radius-sm); overflow-x: auto; max-height: 200px; white-space: pre-wrap; word-break: break-all; font-family: var(--font-mono); font-size: 11px;">${typeof log.response?.body === 'object' ? JSON.stringify(log.response.body, null, 2) : log.response?.body || '—'}</pre>
                                        </div>
                                    </div>
                                </div>
                            `)}
                        </div>
                    `}
                    `}
                </div>
            `}

            <${ConfirmDialog}
                isOpen=${showStop}
                title="Stop Test"
                message="Are you sure you want to stop this test run?"
                onConfirm=${handleStop}
                onCancel=${() => setShowStop(false)}
                confirmLabel=${stopping ? 'Stopping...' : 'Stop'}
                danger=${true}
            />
        </div>
    `;
}
