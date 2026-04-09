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

const html = htm.bind(h);

function fmtNum(n) { if (n == null) return '—'; return n >= 1000 ? (n / 1000).toFixed(1) + 'k' : n.toFixed(1); }
function fmtMs(n) { if (n == null) return '—'; return n >= 1000 ? (n / 1000).toFixed(2) + 's' : n.toFixed(0) + 'ms'; }
function fmtDur(s) { if (!s) return '00:00'; const m = Math.floor(s / 60); const sec = Math.floor(s % 60); return `${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`; }

export function TestRun() {
    const { params } = useRoute();
    const toast = useToast();
    const [status, setStatus] = useState(null);
    const [loading, setLoading] = useState(true);
    const [showStop, setShowStop] = useState(false);
    const [stopping, setStopping] = useState(false);
    const [rpsData, setRpsData] = useState([]);
    const [latencyData, setLatencyData] = useState([]);
    const pollRef = useRef(null);
    const runId = params?.id;
    const engine = params?.engine || 'locust';

    const fetchStatus = async () => {
        if (!runId) return;
        try {
            const res = await apiGet(`/api/${engine}/status/${runId}`);
            if (res) {
                setStatus(res);
                // Append chart data
                const ts = Date.now();
                const totalRps = (res.operations || []).reduce((s, o) => s + (o.rps || 0), 0);
                const avgLat = (res.operations || []).reduce((s, o) => s + (o.avg_response_time || 0), 0) / Math.max((res.operations || []).length, 1);
                setRpsData(prev => [...prev.slice(-120), { time: ts, value: totalRps }]);
                setLatencyData(prev => [...prev.slice(-120), { time: ts, value: avgLat }]);

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
                <div class="metric-card">
                    <div class="metric-value">${fmtDur(elapsed)}</div>
                    <div class="metric-label">Elapsed</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value">${status.user_count || '—'}</div>
                    <div class="metric-label">Users</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value">${fmtNum(totalRps)}</div>
                    <div class="metric-label">RPS</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value">${fmtNum(totalRequests)}</div>
                    <div class="metric-label">Total Requests</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value" style=${totalFailures > 0 ? 'color: var(--color-error)' : ''}>${totalFailures}</div>
                    <div class="metric-label">Failures</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value" style=${parseFloat(errorRate) > 5 ? 'color: var(--color-error)' : ''}>${errorRate}%</div>
                    <div class="metric-label">Error Rate</div>
                </div>
            </div>

            <!-- Charts Row -->
            <div class="form-row" style="margin-bottom: var(--space-4);">
                <div class="card" style="flex: 1;">
                    <h3 style="margin-bottom: var(--space-2); font-size: var(--font-size-sm);">Requests/sec</h3>
                    <${LiveChart} data=${rpsData} color="var(--color-primary)" height=${160} />
                </div>
                <div class="card" style="flex: 1;">
                    <h3 style="margin-bottom: var(--space-2); font-size: var(--font-size-sm);">Avg Latency (ms)</h3>
                    <${LiveChart} data=${latencyData} color="var(--color-warning)" height=${160} />
                </div>
            </div>

            <!-- Per-Operation Stats -->
            <div class="card" style="margin-bottom: var(--space-4);">
                <h3 style="margin-bottom: var(--space-3); font-size: var(--font-size-sm);">Per-Operation Stats</h3>
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
                            </tr>
                        </thead>
                        <tbody>
                            ${(status.operations || []).map(op => html`
                                <tr key=${op.name}>
                                    <td style="font-weight: 500;">${op.name}</td>
                                    <td><span class="badge badge-${op.type === 'mutation' ? 'warning' : 'running'}">${op.type || '—'}</span></td>
                                    <td style="text-align: right;">${op.total_requests || 0}</td>
                                    <td style="text-align: right; ${(op.failures || 0) > 0 ? 'color: var(--color-error);' : ''}">${op.failures || 0}</td>
                                    <td style="text-align: right;">${fmtNum(op.rps || 0)}</td>
                                    <td style="text-align: right;">${fmtMs(op.avg_response_time)}</td>
                                    <td style="text-align: right;">${fmtMs(op.p50)}</td>
                                    <td style="text-align: right;">${fmtMs(op.p90)}</td>
                                    <td style="text-align: right;">${fmtMs(op.p95)}</td>
                                    <td style="text-align: right;">${fmtMs(op.p99)}</td>
                                </tr>
                            `)}
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- Error Log -->
            ${(status.errors || []).length > 0 && html`
                <div class="card">
                    <h3 style="margin-bottom: var(--space-3); font-size: var(--font-size-sm);">Errors (${status.errors.length})</h3>
                    <${ErrorLog} errors=${status.errors} maxHeight="300px" />
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
