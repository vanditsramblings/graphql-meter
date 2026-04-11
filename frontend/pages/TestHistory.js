/**
 * TestHistory.js — Lists test runs with tabs for Running / Completed / Failed / Cleanup.
 */
import { h } from 'preact';
import { useState, useEffect, useRef } from 'preact/hooks';
import htm from 'htm';
import { apiGet, apiPut, apiPost } from '../lib/api.js';
import { useToast } from '../components/Toast.js';
import { navigate } from '../lib/router.js';
import { Spinner } from '../components/Spinner.js';
import { StatusBadge } from '../components/StatusBadge.js';
import { DataTable } from '../components/DataTable.js';
import { Icon } from '../components/Icons.js';

const html = htm.bind(h);

const TABS = ['running', 'completed', 'failed'];

function fmtDate(d) { return d ? new Date(d).toLocaleString() : '—'; }
function fmtDur(s) { if (!s) return '—'; const m = Math.floor(s / 60); return m > 0 ? `${m}m ${Math.round(s % 60)}s` : `${Math.round(s)}s`; }

export function TestHistory() {
    const toast = useToast();
    const [tab, setTab] = useState('running');
    const [runs, setRuns] = useState([]);
    const [loading, setLoading] = useState(true);
    const pollRef = useRef(null);

    const fetchRuns = async () => {
        try {
            const status = tab === 'cleanup' ? 'completed' : tab;
            const res = await apiGet(`/api/results/runs?status=${status}`);
            setRuns(res?.runs || []);
        } catch (e) {
            toast.error('Failed to load runs');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        setLoading(true);
        fetchRuns();
        if (tab === 'running') {
            pollRef.current = setInterval(fetchRuns, 5000);
        }
        return () => { if (pollRef.current) clearInterval(pollRef.current); };
    }, [tab]);

    const handleClick = (run) => {
        if (run.status === 'running') {
            navigate('/test-run', { id: run.id, engine: run.engine || 'locust' });
        } else if (run.status === 'completed' || run.status === 'failed') {
            navigate('/test-run', { id: run.id, engine: run.engine || 'locust' });
        }
    };

    const handleAddNote = async (run) => {
        const note = prompt('Add note for this run:', run.notes || '');
        if (note === null) return;
        try {
            await apiPut(`/api/results/runs/${run.id}/notes`, { notes: note });
            toast.success('Note saved');
            fetchRuns();
        } catch (e) {
            toast.error('Failed to save note');
        }
    };

    const handleCleanup = async (run) => {
        try {
            await apiPost(`/api/cleanup/start/${run.id}`, {});
            toast.success('Cleanup started');
        } catch (e) {
            toast.error(e.message || 'Cleanup failed');
        }
    };

    const columns = [
        { key: 'config_name', label: 'Config', render: (v) => v || '—' },
        { key: 'engine', label: 'Engine', render: (v) => html`<span class="badge">${(v || 'locust').toUpperCase()}</span>` },
        { key: 'status', label: 'Status', render: (v) => html`<${StatusBadge} status=${v} />` },
        { key: 'user_count', label: 'Users', render: (v) => v ?? '—' },
        { key: 'started_at', label: 'Started', render: (v) => fmtDate(v) },
        { key: 'duration_sec', label: 'Duration', render: (v, row) => {
            if (row.status === 'running' && row.started_at) {
                const elapsed = (Date.now() - new Date(row.started_at).getTime()) / 1000;
                return fmtDur(elapsed);
            }
            return fmtDur(v);
        }},
        { key: 'started_by', label: 'User', render: (v) => v || '—' },
        { key: '_actions', label: '', render: (_, row) => html`
            <div class="flex gap-2">
                ${row.status === 'running' && html`
                    <button class="btn btn-ghost btn-sm" onClick=${(e) => { e.stopPropagation(); navigate('/test-run', { id: row.id, engine: row.engine || 'locust' }); }}><${Icon} name="bar-chart" size=${14} /></button>
                `}
                ${row.status === 'completed' && html`
                    <button class="btn btn-ghost btn-sm" title="Add note" onClick=${(e) => { e.stopPropagation(); handleAddNote(row); }}><${Icon} name="edit" size=${14} /></button>
                `}
                ${row.status === 'completed' && html`
                    <button class="btn btn-ghost btn-sm" title="Compare" onClick=${(e) => { e.stopPropagation(); navigate('/compare', { run1: row.id }); }}><${Icon} name="git-compare" size=${14} /></button>
                `}
            </div>
        ` },
    ];

    return html`
        <div>
            <div class="page-header">
                <div>
                    <h1 class="page-title">Test History</h1>
                    <p class="page-subtitle">View and manage test runs</p>
                </div>
            </div>

            <div class="tabs" style="margin-bottom: var(--space-4);">
                ${TABS.map(t => html`
                    <button key=${t} class=${`tab ${tab === t ? 'active' : ''}`}
                        onClick=${() => setTab(t)}>
                        ${t.charAt(0).toUpperCase() + t.slice(1)}
                    </button>
                `)}
            </div>

            ${loading ? html`<${Spinner} />` : html`
                ${runs.length === 0 ? html`
                    <div class="card">
                        <div class="empty-state">
                            <div class="empty-state-icon"><${Icon} name="clipboard" size=${32} /></div>
                            <div class="empty-state-title">No ${tab} runs</div>
                        </div>
                    </div>
                ` : html`
                    <${DataTable} columns=${columns} data=${runs}
                        onRowClick=${handleClick} />
                `}
            `}
        </div>
    `;
}
