/**
 * Dashboard.js — Home page with health status, active runs, and resource usage.
 */
import { h } from 'preact';
import { useState, useEffect } from 'preact/hooks';
import htm from 'htm';
import { apiGet } from '../lib/api.js';
import { StatusBadge } from '../components/StatusBadge.js';
import { Spinner } from '../components/Spinner.js';

const html = htm.bind(h);

export function Dashboard() {
    const [health, setHealth] = useState(null);
    const [resources, setResources] = useState(null);
    const [storageStatus, setStorageStatus] = useState(null);
    const [loading, setLoading] = useState(true);

    const fetchData = async () => {
        try {
            const [h, r, s] = await Promise.all([
                apiGet('/api/health/status').catch(() => null),
                apiGet('/api/health/resources').catch(() => null),
                apiGet('/api/storage/status').catch(() => null),
            ]);
            setHealth(h);
            setResources(r);
            setStorageStatus(s);
        } catch (e) {
            console.error('Dashboard fetch error:', e);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchData();
        const interval = setInterval(fetchData, 5000);
        return () => clearInterval(interval);
    }, []);

    if (loading) {
        return html`<${Spinner} size="lg" message="Loading dashboard..." />`;
    }

    const cpuLevel = resources?.cpu_percent > 80 ? 'high' : resources?.cpu_percent > 50 ? 'medium' : 'low';
    const memLevel = resources?.memory?.system_percent > 80 ? 'high' : resources?.memory?.system_percent > 50 ? 'medium' : 'low';

    return html`
        <div>
            <div class="page-header">
                <div>
                    <h1 class="page-title">Dashboard</h1>
                    <p class="page-subtitle">System overview and active tests</p>
                </div>
            </div>

            <!-- Status Cards -->
            <div class="card-grid card-grid-4 mb-6">
                <div class="stat-card">
                    <div class="stat-label">System Status</div>
                    <div class="stat-value ${health?.status === 'ok' ? 'success' : 'error'}">
                        ${health?.status === 'ok' ? 'Healthy' : 'Error'}
                    </div>
                    <div class="stat-detail">Uptime: ${health?.uptime || '—'}</div>
                </div>

                <div class="stat-card">
                    <div class="stat-label">Test Configs</div>
                    <div class="stat-value">${storageStatus?.test_configs ?? '—'}</div>
                    <div class="stat-detail">Saved configurations</div>
                </div>

                <div class="stat-card">
                    <div class="stat-label">Total Runs</div>
                    <div class="stat-value">${storageStatus?.test_runs ?? '—'}</div>
                    <div class="stat-detail">Historical test runs</div>
                </div>

                <div class="stat-card">
                    <div class="stat-label">Version</div>
                    <div class="stat-value" style="font-size: var(--font-size-xl);">${health?.version || '—'}</div>
                    <div class="stat-detail">GraphQL Meter</div>
                </div>
            </div>

            <!-- Resource Usage -->
            <div class="card-grid card-grid-2 mb-6">
                <div class="card">
                    <div class="card-header">
                        <h3 class="card-title">CPU Usage</h3>
                        <span class="text-muted">${resources?.cpu_count || 0} cores</span>
                    </div>
                    <div style="display: flex; align-items: baseline; gap: var(--space-2); margin-bottom: var(--space-3);">
                        <span style="font-size: var(--font-size-2xl); font-weight: 700;">${resources?.cpu_percent?.toFixed(1) || 0}%</span>
                    </div>
                    <div class="resource-bar">
                        <div class="resource-bar-fill ${cpuLevel}" style="width: ${resources?.cpu_percent || 0}%"></div>
                    </div>
                </div>

                <div class="card">
                    <div class="card-header">
                        <h3 class="card-title">Memory Usage</h3>
                        <span class="text-muted">${resources?.memory?.system_total_mb ? (resources.memory.system_total_mb / 1024).toFixed(1) + ' GB' : '—'}</span>
                    </div>
                    <div style="display: flex; align-items: baseline; gap: var(--space-2); margin-bottom: var(--space-3);">
                        <span style="font-size: var(--font-size-2xl); font-weight: 700;">${resources?.memory?.system_percent?.toFixed(1) || 0}%</span>
                        <span class="text-muted" style="font-size: var(--font-size-sm);">
                            (Process: ${resources?.memory?.process_rss_mb?.toFixed(0) || 0} MB)
                        </span>
                    </div>
                    <div class="resource-bar">
                        <div class="resource-bar-fill ${memLevel}" style="width: ${resources?.memory?.system_percent || 0}%"></div>
                    </div>
                </div>
            </div>

            <!-- Active Runs -->
            <div class="card">
                <div class="card-header">
                    <h3 class="card-title">Active Test Runs</h3>
                </div>
                <div class="empty-state" style="padding: var(--space-6);">
                    <div class="empty-state-icon">⚡</div>
                    <div class="empty-state-title">No Active Runs</div>
                    <div class="empty-state-description">Start a test from the Test Configs page to see live results here.</div>
                </div>
            </div>
        </div>
    `;
}
