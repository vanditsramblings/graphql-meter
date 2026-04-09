/**
 * TestConfigs.js — 3-step wizard for creating/editing test configurations.
 * Step 1: Global params + schema → Parse
 * Step 2: Operations selection, TPS%, delay, test data
 * Step 3: Review + engine selector + save/start
 */
import { h } from 'preact';
import { useState, useEffect } from 'preact/hooks';
import htm from 'htm';
import { apiGet, apiPost, apiDelete } from '../lib/api.js';
import { useAuth } from '../lib/auth.js';
import { useToast } from '../components/Toast.js';
import { navigate } from '../lib/router.js';
import { Spinner } from '../components/Spinner.js';
import { Modal } from '../components/Modal.js';
import { ConfirmDialog } from '../components/ConfirmDialog.js';
import { WizardStepper } from '../components/WizardStepper.js';
import { PercentageBar } from '../components/PercentageBar.js';
import { Accordion } from '../components/Accordion.js';
import { StatusBadge } from '../components/StatusBadge.js';

const html = htm.bind(h);

function ConfigList({ configs, onEdit, onNew, onDelete }) {
    if (!configs || configs.length === 0) {
        return html`
            <div class="card">
                <div class="empty-state">
                    <div class="empty-state-icon">⚙</div>
                    <div class="empty-state-title">No Test Configurations</div>
                    <div class="empty-state-description">Create your first test configuration to get started.</div>
                    <button class="btn btn-primary" onClick=${onNew}>+ New Configuration</button>
                </div>
            </div>
        `;
    }

    return html`
        <div>
            ${configs.map(c => html`
                <div key=${c.id} class="card" style="margin-bottom: var(--space-3); cursor: pointer;"
                    onClick=${() => onEdit(c.id)}>
                    <div class="flex items-center justify-between">
                        <div>
                            <div style="font-weight: 600; font-size: var(--font-size-base);">${c.name}</div>
                            <div class="text-muted" style="font-size: var(--font-size-xs);">
                                ${c.description || 'No description'} · Created by ${c.created_by || '—'} · ${c.updated_at ? new Date(c.updated_at).toLocaleDateString() : ''}
                            </div>
                        </div>
                        <div class="flex gap-2">
                            <button class="btn btn-ghost btn-sm" onClick=${(e) => { e.stopPropagation(); onDelete(c); }}>🗑</button>
                        </div>
                    </div>
                </div>
            `)}
        </div>
    `;
}

const DEFAULT_GLOBAL = {
    name: '', description: '', host: '', platform: 'cloud',
    user_count: 10, ramp_up_sec: 10, duration_sec: 60, graphql_path: '/graphql',
    environment_id: '',
};

export function TestConfigs() {
    const { hasFlag } = useAuth();
    const toast = useToast();
    const [configs, setConfigs] = useState([]);
    const [loading, setLoading] = useState(true);
    const [showWizard, setShowWizard] = useState(false);
    const [step, setStep] = useState(1);
    const [editId, setEditId] = useState(null);
    const [deleteTarget, setDeleteTarget] = useState(null);

    // Wizard state
    const [globalParams, setGlobalParams] = useState({ ...DEFAULT_GLOBAL });
    const [schemaText, setSchemaText] = useState('');
    const [parsedOps, setParsedOps] = useState([]);
    const [operations, setOperations] = useState([]);
    const [engine, setEngine] = useState('locust');
    const [debugMode, setDebugMode] = useState(false);
    const [cleanupOnStop, setCleanupOnStop] = useState(false);
    const [parsing, setParsing] = useState(false);
    const [saving, setSaving] = useState(false);
    const [authProviders, setAuthProviders] = useState([]);
    const [authProviderId, setAuthProviderId] = useState('');
    const [environments, setEnvironments] = useState([]);

    const fetchConfigs = async () => {
        try {
            const res = await apiGet('/api/testconfig/list');
            setConfigs(res?.configs || []);
        } catch (e) {
            toast.error('Failed to load configs');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => { fetchConfigs(); }, []);

    // Load auth providers and environments for the wizard
    const loadWizardData = async () => {
        try {
            const [ap, env] = await Promise.all([
                apiGet('/api/authproviders/list').catch(() => ({ providers: [] })),
                apiGet('/api/environments/list').catch(() => ({ environments: [] })),
            ]);
            setAuthProviders(ap?.providers || []);
            setEnvironments(env?.environments || []);
        } catch (e) { /* ignore */ }
    };

    const openNew = () => {
        setEditId(null);
        setGlobalParams({ ...DEFAULT_GLOBAL });
        setSchemaText('');
        setParsedOps([]);
        setOperations([]);
        setEngine('locust');
        setDebugMode(false);
        setCleanupOnStop(false);
        setAuthProviderId('');
        setStep(1);
        setShowWizard(true);
        loadWizardData();
    };

    const openEdit = async (id) => {
        try {
            const cfg = await apiGet(`/api/testconfig/${id}`);
            if (!cfg) return;
            setEditId(id);
            const cj = typeof cfg.config_json === 'string' ? JSON.parse(cfg.config_json) : (cfg.config_json || {});
            setGlobalParams({ ...DEFAULT_GLOBAL, ...cj.global_params, name: cfg.name, description: cfg.description || '' });
            setSchemaText(cfg.schema_text || '');
            setOperations(cj.operations || []);
            setParsedOps(cj.operations || []);
            setEngine(cj.engine || 'locust');
            setDebugMode(cj.debug_mode || false);
            setCleanupOnStop(cj.cleanup_on_stop || false);
            setAuthProviderId(cj.auth_provider_id || '');
            setStep(1);
            setShowWizard(true);
            loadWizardData();
        } catch (e) {
            toast.error('Failed to load config');
        }
    };

    const handleParseSchema = async () => {
        if (!schemaText.trim()) { toast.warning('Paste a schema first'); return; }
        setParsing(true);
        try {
            const res = await apiPost('/api/schema/parse', { schema_text: schemaText });
            if (res?.operations) {
                const ops = res.operations.map(op => ({
                    name: op.name,
                    type: op.type,
                    query: op.query || '',
                    enabled: true,
                    tps_percentage: 0,
                    delay_start_sec: 0,
                    data_range_start: 1,
                    data_range_end: 100,
                    variables: (op.variables || []).map(v => ({
                        name: v.name, type: v.type,
                        value: v.default_value ?? '', required: v.required,
                    })),
                }));

                // Distribute TPS% evenly
                const perOp = Math.floor(100 / ops.length);
                ops.forEach((op, i) => {
                    op.tps_percentage = i === ops.length - 1 ? 100 - perOp * (ops.length - 1) : perOp;
                });

                setParsedOps(ops);
                setOperations(ops);
                toast.success(`Found ${ops.length} operations`);
                setStep(2);
            }
        } catch (e) {
            toast.error(e.message || 'Schema parse failed');
        } finally {
            setParsing(false);
        }
    };

    const updateOp = (idx, field, value) => {
        setOperations(prev => prev.map((op, i) => i === idx ? { ...op, [field]: value } : op));
    };

    const updateVar = (opIdx, varIdx, field, value) => {
        setOperations(prev => prev.map((op, i) => {
            if (i !== opIdx) return op;
            const vars = op.variables.map((v, vi) => vi === varIdx ? { ...v, [field]: value } : v);
            return { ...op, variables: vars };
        }));
    };

    const handleSave = async (autoStart = false) => {
        setSaving(true);
        try {
            const payload = {
                id: editId,
                name: globalParams.name,
                description: globalParams.description,
                schema_text: schemaText,
                config_json: {
                    global_params: globalParams,
                    operations: operations,
                    engine: engine,
                    debug_mode: debugMode,
                    cleanup_on_stop: cleanupOnStop,
                    auth_provider_id: authProviderId,
                },
            };
            const res = await apiPost('/api/testconfig/save', payload);
            if (res) {
                toast.success(editId ? 'Config updated' : 'Config saved');
                setShowWizard(false);
                fetchConfigs();

                if (autoStart) {
                    const enginePath = engine === 'k6' ? 'k6' : 'locust';
                    const startRes = await apiPost(`/api/${enginePath}/start`, {
                        config_id: res.id || editId,
                        name: globalParams.name,
                        global_params: globalParams,
                        operations: operations.filter(o => o.enabled),
                        engine: engine,
                        debug_mode: debugMode,
                        cleanup_on_stop: cleanupOnStop,
                        auth_provider_id: authProviderId,
                    });
                    if (startRes?.run_id) {
                        toast.success('Test started!');
                        navigate('/test-run', { id: startRes.run_id, engine: enginePath });
                    }
                }
            }
        } catch (e) {
            toast.error(e.message || 'Save failed');
        } finally {
            setSaving(false);
        }
    };

    const handleDelete = async () => {
        if (!deleteTarget) return;
        try {
            await apiDelete(`/api/testconfig/${deleteTarget.id}`);
            toast.success('Config deleted');
            setDeleteTarget(null);
            fetchConfigs();
        } catch (e) {
            toast.error(e.message || 'Delete failed');
        }
    };

    const enabledOps = operations.filter(o => o.enabled);
    const totalTps = enabledOps.reduce((s, o) => s + (o.tps_percentage || 0), 0);
    const tpsValid = Math.abs(totalTps - 100) < 0.1;

    if (loading) return html`<${Spinner} size="lg" message="Loading..." />`;

    return html`
        <div>
            <div class="page-header">
                <div>
                    <h1 class="page-title">Test Configurations</h1>
                    <p class="page-subtitle">Create and manage load test configurations</p>
                </div>
                ${hasFlag('configs.create') && html`
                    <button class="btn btn-primary" onClick=${openNew}>+ New Configuration</button>
                `}
            </div>

            ${!showWizard && html`
                <${ConfigList} configs=${configs} onEdit=${openEdit} onNew=${openNew} onDelete=${(c) => setDeleteTarget(c)} />
            `}

            ${showWizard && html`
                <div class="card">
                    <${WizardStepper} steps=${['Schema & Params', 'Operations', 'Review & Run']} currentStep=${step} />

                    ${step === 1 && html`
                        <div>
                            <div class="form-row">
                                <div class="form-group">
                                    <label class="form-label">Configuration Name *</label>
                                    <input class="form-input" value=${globalParams.name}
                                        onInput=${(e) => setGlobalParams(p => ({ ...p, name: e.target.value }))}
                                        placeholder="e.g., Customer API Load Test" />
                                </div>
                                <div class="form-group">
                                    <label class="form-label">Description</label>
                                    <input class="form-input" value=${globalParams.description}
                                        onInput=${(e) => setGlobalParams(p => ({ ...p, description: e.target.value }))}
                                        placeholder="Optional description" />
                                </div>
                            </div>
                            <div class="form-row-3">
                                <div class="form-group">
                                    <label class="form-label">Host URL *</label>
                                    <input class="form-input" value=${globalParams.host}
                                        onInput=${(e) => setGlobalParams(p => ({ ...p, host: e.target.value }))}
                                        placeholder="https://api.example.com" />
                                </div>
                                <div class="form-group">
                                    <label class="form-label">GraphQL Path</label>
                                    <input class="form-input" value=${globalParams.graphql_path}
                                        onInput=${(e) => setGlobalParams(p => ({ ...p, graphql_path: e.target.value }))} />
                                </div>
                                <div class="form-group">
                                    <label class="form-label">Platform</label>
                                    <select class="form-select" value=${globalParams.platform}
                                        onChange=${(e) => setGlobalParams(p => ({ ...p, platform: e.target.value }))}>
                                        <option value="cloud">Cloud</option>
                                        <option value="onprem">On-Premises</option>
                                    </select>
                                </div>
                            </div>
                            <div class="form-row-3">
                                <div class="form-group">
                                    <label class="form-label">Users</label>
                                    <input class="form-input" type="number" min="1" value=${globalParams.user_count}
                                        onInput=${(e) => setGlobalParams(p => ({ ...p, user_count: parseInt(e.target.value) || 1 }))} />
                                </div>
                                <div class="form-group">
                                    <label class="form-label">Ramp-up (sec)</label>
                                    <input class="form-input" type="number" min="0" value=${globalParams.ramp_up_sec}
                                        onInput=${(e) => setGlobalParams(p => ({ ...p, ramp_up_sec: parseInt(e.target.value) || 0 }))} />
                                </div>
                                <div class="form-group">
                                    <label class="form-label">Duration (sec)</label>
                                    <input class="form-input" type="number" min="10" value=${globalParams.duration_sec}
                                        onInput=${(e) => setGlobalParams(p => ({ ...p, duration_sec: parseInt(e.target.value) || 60 }))} />
                                </div>
                            </div>
                            <div class="form-row">
                                <div class="form-group">
                                    <label class="form-label">Environment</label>
                                    <select class="form-select" value=${globalParams.environment_id || ''}
                                        onChange=${(e) => {
                                            const env = environments.find(en => en.id === e.target.value);
                                            setGlobalParams(p => ({
                                                ...p, environment_id: e.target.value,
                                                host: env ? env.base_url : p.host,
                                                graphql_path: env ? env.graphql_path : p.graphql_path,
                                                platform: env ? env.platform : p.platform,
                                            }));
                                        }}>
                                        <option value="">— None —</option>
                                        ${environments.map(e => html`<option key=${e.id} value=${e.id}>${e.name} (${e.base_url})</option>`)}
                                    </select>
                                </div>
                                <div class="form-group">
                                    <label class="form-label">Auth Provider</label>
                                    <select class="form-select" value=${authProviderId}
                                        onChange=${(e) => setAuthProviderId(e.target.value)}>
                                        <option value="">— None —</option>
                                        ${authProviders.map(ap => html`<option key=${ap.id} value=${ap.id}>${ap.name} (${ap.auth_type})</option>`)}
                                    </select>
                                </div>
                            </div>
                            <div class="form-group">
                                <label class="form-label">GraphQL Schema *</label>
                                <textarea class="form-textarea" rows="12" value=${schemaText}
                                    onInput=${(e) => setSchemaText(e.target.value)}
                                    placeholder="Paste your GraphQL schema here..." />
                            </div>
                            <div class="flex justify-between mt-4">
                                <button class="btn btn-secondary" onClick=${() => setShowWizard(false)}>Cancel</button>
                                <button class="btn btn-primary" onClick=${handleParseSchema}
                                    disabled=${parsing || !schemaText.trim() || !globalParams.name || !globalParams.host}>
                                    ${parsing ? 'Parsing...' : 'Parse Schema →'}
                                </button>
                            </div>
                        </div>
                    `}

                    ${step === 2 && html`
                        <div>
                            <div style="margin-bottom: var(--space-4);">
                                <${PercentageBar} segments=${enabledOps.map(o => ({ label: o.name, value: o.tps_percentage }))} />
                            </div>

                            ${operations.map((op, i) => html`
                                <${Accordion} key=${op.name} title="${op.type === 'mutation' ? '🔸' : '🔹'} ${op.name}" defaultOpen=${i === 0}
                                    badge=${op.enabled ? op.tps_percentage + '%' : 'off'}>
                                    <div style="padding-top: var(--space-3);">
                                        <div class="flex items-center gap-4 mb-4">
                                            <label class="flex items-center gap-2" style="cursor: pointer;">
                                                <input type="checkbox" checked=${op.enabled}
                                                    onChange=${(e) => updateOp(i, 'enabled', e.target.checked)} />
                                                Enabled
                                            </label>
                                            <span class="badge badge-${op.type === 'mutation' ? 'warning' : 'running'}">${op.type}</span>
                                        </div>

                                        ${op.enabled && html`
                                            <div class="form-row-3 mb-4">
                                                <div class="form-group">
                                                    <label class="form-label">TPS %</label>
                                                    <input class="form-input" type="number" min="0" max="100" step="0.1"
                                                        value=${op.tps_percentage}
                                                        onInput=${(e) => updateOp(i, 'tps_percentage', parseFloat(e.target.value) || 0)} />
                                                </div>
                                                <div class="form-group">
                                                    <label class="form-label">Delay Start (sec)</label>
                                                    <input class="form-input" type="number" min="0" value=${op.delay_start_sec}
                                                        onInput=${(e) => updateOp(i, 'delay_start_sec', parseInt(e.target.value) || 0)} />
                                                </div>
                                                <div class="form-group">
                                                    <label class="form-label">Data Range</label>
                                                    <div class="flex gap-2">
                                                        <input class="form-input" type="number" style="width: 80px;" value=${op.data_range_start}
                                                            onInput=${(e) => updateOp(i, 'data_range_start', parseInt(e.target.value) || 1)} />
                                                        <span class="text-muted" style="line-height: 2.2;">to</span>
                                                        <input class="form-input" type="number" style="width: 80px;" value=${op.data_range_end}
                                                            onInput=${(e) => updateOp(i, 'data_range_end', parseInt(e.target.value) || 100)} />
                                                    </div>
                                                </div>
                                            </div>

                                            ${op.variables && op.variables.length > 0 && html`
                                                <div style="margin-bottom: var(--space-3);">
                                                    <div class="form-label">Variables</div>
                                                    ${op.variables.map((v, vi) => html`
                                                        <div key=${v.name} class="form-row" style="margin-bottom: var(--space-2);">
                                                            <div class="flex items-center gap-2">
                                                                <span class="text-mono text-muted" style="min-width: 120px; font-size: var(--font-size-xs);">
                                                                    ${v.name}${v.required ? ' *' : ''}
                                                                </span>
                                                                <span class="text-muted" style="font-size: var(--font-size-xs);">(${v.type})</span>
                                                            </div>
                                                            <input class="form-input" style="font-family: var(--font-mono); font-size: var(--font-size-xs);"
                                                                value=${typeof v.value === 'object' ? JSON.stringify(v.value) : v.value}
                                                                onInput=${(e) => {
                                                                    let val = e.target.value;
                                                                    try { val = JSON.parse(val); } catch {}
                                                                    updateVar(i, vi, 'value', val);
                                                                }} />
                                                        </div>
                                                    `)}
                                                </div>
                                            `}

                                            <div class="form-group">
                                                <label class="form-label">Query</label>
                                                <textarea class="form-textarea" rows="4" value=${op.query}
                                                    onInput=${(e) => updateOp(i, 'query', e.target.value)} />
                                            </div>
                                        `}
                                    </div>
                                </${Accordion}>
                            `)}

                            <div class="flex justify-between mt-4">
                                <button class="btn btn-secondary" onClick=${() => setStep(1)}>← Back</button>
                                <button class="btn btn-primary" onClick=${() => setStep(3)}
                                    disabled=${!tpsValid || enabledOps.length === 0}>
                                    ${!tpsValid ? `TPS% = ${totalTps.toFixed(1)} (need 100)` : 'Review →'}
                                </button>
                            </div>
                        </div>
                    `}

                    ${step === 3 && html`
                        <div>
                            <div class="card" style="margin-bottom: var(--space-4); background: var(--bg-tertiary);">
                                <h3 style="margin-bottom: var(--space-3); font-size: var(--font-size-base);">Configuration Summary</h3>
                                <div class="form-row-3" style="font-size: var(--font-size-sm);">
                                    <div><span class="text-muted">Name:</span> ${globalParams.name}</div>
                                    <div><span class="text-muted">Host:</span> ${globalParams.host}</div>
                                    <div><span class="text-muted">Platform:</span> ${globalParams.platform}</div>
                                    <div><span class="text-muted">Users:</span> ${globalParams.user_count}</div>
                                    <div><span class="text-muted">Ramp-up:</span> ${globalParams.ramp_up_sec}s</div>
                                    <div><span class="text-muted">Duration:</span> ${globalParams.duration_sec}s</div>
                                </div>
                                <div style="margin-top: var(--space-3); font-size: var(--font-size-sm);">
                                    <span class="text-muted">Operations:</span> ${enabledOps.length} enabled (${operations.length} total)
                                </div>
                                ${authProviderId && html`
                                    <div style="margin-top: var(--space-2); font-size: var(--font-size-sm);">
                                        <span class="text-muted">Auth:</span> ${authProviders.find(a => a.id === authProviderId)?.name || authProviderId}
                                    </div>
                                `}
                            </div>

                            <div class="form-row mb-4">
                                <div class="form-group">
                                    <label class="form-label">Load Engine</label>
                                    <select class="form-select" value=${engine} onChange=${(e) => setEngine(e.target.value)}>
                                        <option value="locust">Locust (Python)</option>
                                        <option value="k6">k6 (Go)</option>
                                    </select>
                                </div>
                                <div class="form-group">
                                    <label class="form-label">Options</label>
                                    <div class="flex gap-4" style="padding-top: var(--space-2);">
                                        <label class="flex items-center gap-2" style="cursor: pointer; font-size: var(--font-size-sm);">
                                            <input type="checkbox" checked=${debugMode} onChange=${(e) => setDebugMode(e.target.checked)} />
                                            Debug Mode
                                        </label>
                                        <label class="flex items-center gap-2" style="cursor: pointer; font-size: var(--font-size-sm);">
                                            <input type="checkbox" checked=${cleanupOnStop} onChange=${(e) => setCleanupOnStop(e.target.checked)} />
                                            Cleanup on Stop
                                        </label>
                                    </div>
                                </div>
                            </div>

                            <div class="flex justify-between mt-4">
                                <button class="btn btn-secondary" onClick=${() => setStep(2)}>← Back</button>
                                <div class="flex gap-3">
                                    <button class="btn btn-secondary" onClick=${() => handleSave(false)} disabled=${saving}>
                                        ${saving ? 'Saving...' : 'Save'}
                                    </button>
                                    <button class="btn btn-primary" onClick=${() => handleSave(true)} disabled=${saving}>
                                        ${saving ? 'Starting...' : '▶ Save & Start Test'}
                                    </button>
                                </div>
                            </div>
                        </div>
                    `}
                </div>
            `}

            <${ConfirmDialog}
                isOpen=${!!deleteTarget}
                title="Delete Configuration"
                message=${`Delete "${deleteTarget?.name}"? This cannot be undone.`}
                onConfirm=${handleDelete}
                onCancel=${() => setDeleteTarget(null)}
                confirmLabel="Delete"
                danger=${true}
            />
        </div>
    `;
}
