/**
 * Settings.js — Runtime configuration management page (admin only).
 * Reads current config from /api/health/config/validate, saves via PUT /api/health/config.
 */
import { h } from 'preact';
import { useState, useEffect } from 'preact/hooks';
import htm from 'htm';
import { apiGet, apiPut } from '../lib/api.js';
import { useAuth } from '../lib/auth.js';
import { useToast } from '../components/Toast.js';
import { Spinner } from '../components/Spinner.js';
import { Icon } from '../components/Icons.js';

const html = htm.bind(h);

const CONFIG_FIELDS = [
    { section: 'Load Testing', fields: [
        { key: 'max_concurrent_runs', label: 'Max Concurrent Runs', type: 'number', min: 1, max: 20, help: 'Maximum simultaneous test runs allowed.' },
        { key: 'max_error_buffer', label: 'Max Error Buffer', type: 'number', min: 50, max: 5000, help: 'Maximum error lines kept per run.' },
        { key: 'max_run_history', label: 'Max Run History', type: 'number', min: 10, max: 10000, help: 'Maximum runs retained in history.' },
        { key: 'chart_history_runs', label: 'Chart History Runs', type: 'number', min: 1, max: 100, help: 'Runs with full chart data retained.' },
    ]},
    { section: 'Engine Toggles', fields: [
        { key: 'enable_k6', label: 'Enable k6 Engine', type: 'toggle', help: 'Allow starting tests with the k6 engine.' },
        { key: 'enable_locust', label: 'Enable Locust Engine', type: 'toggle', help: 'Allow starting tests with the Locust engine.' },
    ]},
    { section: 'Performance', fields: [
        { key: 'worker_threads', label: 'Worker Threads', type: 'number', min: 1, max: 32, help: 'Background worker thread count.' },
        { key: 'dashboard_poll_sec', label: 'Dashboard Poll (sec)', type: 'number', min: 1, max: 60, help: 'Dashboard refresh interval.' },
        { key: 'running_test_poll_sec', label: 'Live Test Poll (sec)', type: 'number', min: 1, max: 30, help: 'Live test page refresh interval.' },
    ]},
    { section: 'Debug', fields: [
        { key: 'debug', label: 'Debug Mode', type: 'toggle', help: 'Enable verbose debug logging.' },
    ]},
];

function ToggleField({ field, value, onChange, disabled }) {
    return html`
        <label style="display: inline-flex; align-items: center; cursor: pointer; gap: var(--space-2);">
            <input
                type="checkbox"
                checked=${value}
                onChange=${(e) => onChange(field.key, e.target.checked)}
                disabled=${disabled}
                style="width: 18px; height: 18px; accent-color: var(--color-primary);"
            />
            <span style="color: var(--color-text-secondary); font-size: 0.85rem;">${value ? 'On' : 'Off'}</span>
        </label>
    `;
}

function NumberField({ field, value, onChange, disabled }) {
    return html`
        <input
            type="number"
            class="form-input"
            value=${value}
            min=${field.min}
            max=${field.max}
            onInput=${(e) => onChange(field.key, parseInt(e.target.value, 10) || 0)}
            disabled=${disabled}
            style="width: 100px; text-align: right;"
        />
    `;
}

function ConfigRow({ field, value, onChange, disabled }) {
    return html`
        <div style="display: flex; align-items: center; justify-content: space-between; padding: var(--space-3) 0; border-bottom: 1px solid var(--color-border);">
            <div style="flex: 1;">
                <div style="font-weight: 500; color: var(--color-text-primary);">${field.label}</div>
                <div style="font-size: 0.8rem; color: var(--color-text-secondary); margin-top: 2px;">${field.help}</div>
            </div>
            <div style="width: 160px; text-align: right;">
                ${field.type === 'toggle'
                    ? html`<${ToggleField} field=${field} value=${value} onChange=${onChange} disabled=${disabled} />`
                    : html`<${NumberField} field=${field} value=${value} onChange=${onChange} disabled=${disabled} />`
                }
            </div>
        </div>
    `;
}

export function Settings() {
    const { user } = useAuth();
    const toast = useToast();
    const [config, setConfig] = useState(null);
    const [form, setForm] = useState({});
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [serverInfo, setServerInfo] = useState(null);

    const isAdmin = user?.role === 'admin';

    const fetchConfig = async () => {
        try {
            const [cfg, info] = await Promise.all([
                apiGet('/api/health/config/validate'),
                apiGet('/api/health/status'),
            ]);
            setConfig(cfg);
            setForm({ ...cfg });
            setServerInfo(info);
        } catch (e) {
            toast.error('Failed to load configuration');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => { fetchConfig(); }, []);

    const handleChange = (key, value) => {
        setForm(prev => ({ ...prev, [key]: value }));
    };

    const hasChanges = () => {
        if (!config) return false;
        return Object.keys(form).some(k => form[k] !== config[k]);
    };

    const handleSave = async () => {
        if (!isAdmin) { toast.warning('Admin access required'); return; }
        const changes = {};
        for (const key of Object.keys(form)) {
            if (form[key] !== config[key]) changes[key] = form[key];
        }
        if (Object.keys(changes).length === 0) { toast.info('No changes to save'); return; }

        setSaving(true);
        try {
            const res = await apiPut('/api/health/config', changes);
            const count = Object.keys(res?.updated || {}).length;
            toast.success('Configuration updated (' + count + ' fields)');
            setConfig({ ...form });
        } catch (e) {
            toast.error('Failed to save: ' + e.message);
        } finally {
            setSaving(false);
        }
    };

    const handleReset = () => {
        if (config) setForm({ ...config });
    };

    if (loading) {
        return html`<${Spinner} size="lg" message="Loading settings..." />`;
    }

    const changed = hasChanges();

    return html`
        <div>
            <div class="page-header">
                <div>
                    <h1 class="page-title">Settings</h1>
                    <p class="page-subtitle">Runtime configuration — changes persist until server restart</p>
                </div>
                <div class="page-actions">
                    ${changed && html`
                        <button class="btn btn-ghost" onClick=${handleReset} disabled=${saving}>
                            <${Icon} name="x" size=${14} /> Discard
                        </button>
                    `}
                    <button class="btn btn-primary" onClick=${handleSave} disabled=${!changed || saving || !isAdmin}>
                        <${Icon} name="save" size=${14} /> ${saving ? 'Saving...' : 'Save Changes'}
                    </button>
                </div>
            </div>

            ${!isAdmin && html`
                <div style="padding: var(--space-3); border-radius: var(--radius-md); background: rgba(255, 152, 0, 0.1); border: 1px solid rgba(255, 152, 0, 0.3); color: var(--color-warning); margin-bottom: var(--space-4);">
                    <${Icon} name="shield" size=${14} /> Admin access required to modify settings. Viewing current values only.
                </div>
            `}

            ${serverInfo && html`
                <div class="card-grid card-grid-4 mb-6">
                    <div class="stat-card">
                        <div class="stat-label">Version</div>
                        <div class="stat-value" style="font-size: 1rem">${serverInfo.version || '—'}</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">Uptime</div>
                        <div class="stat-value" style="font-size: 1rem">${serverInfo.uptime || '—'}</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">k6 Engine</div>
                        <div class="stat-value ${form.enable_k6 ? 'success' : 'error'}" style="font-size: 1rem">${form.enable_k6 ? 'Enabled' : 'Disabled'}</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">Locust Engine</div>
                        <div class="stat-value ${form.enable_locust ? 'success' : 'error'}" style="font-size: 1rem">${form.enable_locust ? 'Enabled' : 'Disabled'}</div>
                    </div>
                </div>
            `}

            ${CONFIG_FIELDS.map(section => html`
                <div class="card mb-4">
                    <div class="card-header">
                        <h3 class="card-title">${section.section}</h3>
                    </div>
                    <div class="card-body">
                        ${section.fields.map(field => html`
                            <${ConfigRow}
                                field=${field}
                                value=${form[field.key]}
                                onChange=${handleChange}
                                disabled=${!isAdmin}
                            />
                        `)}
                    </div>
                </div>
            `)}
        </div>
    `;
}
