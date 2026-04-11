/**
 * AuthProviders.js — CRUD management for authentication providers.
 * Renders dynamic form fields based on auth_type from /api/authproviders/types.
 */
import { h } from 'preact';
import { useState, useEffect } from 'preact/hooks';
import htm from 'htm';
import { apiGet, apiPost, apiDelete } from '../lib/api.js';
import { useAuth } from '../lib/auth.js';
import { useToast } from '../components/Toast.js';
import { Spinner } from '../components/Spinner.js';
import { Modal } from '../components/Modal.js';
import { ConfirmDialog } from '../components/ConfirmDialog.js';
import { StatusBadge } from '../components/StatusBadge.js';
import { Icon } from '../components/Icons.js';

const html = htm.bind(h);

const AUTH_TYPE_LABELS = {
    bearer_token: 'Bearer Token',
    basic: 'Basic Auth',
    api_key: 'API Key',
    oauth2_client_credentials: 'OAuth2 Client Credentials',
    oauth2_password: 'OAuth2 Password',
    jwt_custom: 'Custom JWT',
};

function FieldInput({ field, value, onChange }) {
    const val = value ?? field.default ?? '';
    if (field.type === 'select' && field.options) {
        return html`
            <select class="form-select" value=${val} onChange=${(e) => onChange(e.target.value)}>
                ${field.options.map(o => html`<option key=${o} value=${o}>${o}</option>`)}
            </select>
        `;
    }
    if (field.type === 'textarea') {
        return html`
            <textarea class="form-textarea" rows="3" value=${val}
                onInput=${(e) => onChange(e.target.value)}
                placeholder=${field.help || ''} />
        `;
    }
    if (field.type === 'number') {
        return html`
            <input class="form-input" type="number" value=${val}
                onInput=${(e) => onChange(parseInt(e.target.value) || 0)} />
        `;
    }
    const inputType = field.type === 'password' ? 'password' : 'text';
    return html`
        <input class="form-input" type=${inputType} value=${val}
            onInput=${(e) => onChange(e.target.value)}
            placeholder=${field.help || ''} />
    `;
}

export function AuthProviders() {
    const { hasFlag } = useAuth();
    const toast = useToast();
    const [providers, setProviders] = useState([]);
    const [typeSchemas, setTypeSchemas] = useState({});
    const [loading, setLoading] = useState(true);
    const [showForm, setShowForm] = useState(false);
    const [editProvider, setEditProvider] = useState(null);
    const [formType, setFormType] = useState('bearer_token');
    const [formName, setFormName] = useState('');
    const [formDesc, setFormDesc] = useState('');
    const [formConfig, setFormConfig] = useState({});
    const [saving, setSaving] = useState(false);
    const [testing, setTesting] = useState(false);
    const [testResult, setTestResult] = useState(null);
    const [deleteTarget, setDeleteTarget] = useState(null);
    const [search, setSearch] = useState('');
    const [filterType, setFilterType] = useState('');

    const fetchProviders = async () => {
        try {
            const [pRes, tRes] = await Promise.all([
                apiGet('/api/authproviders/list'),
                apiGet('/api/authproviders/types'),
            ]);
            setProviders(pRes?.providers || []);
            setTypeSchemas(tRes?.types || {});
        } catch (e) {
            toast.error('Failed to load auth providers');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => { fetchProviders(); }, []);

    const openNew = () => {
        setEditProvider(null);
        setFormType('bearer_token');
        setFormName('');
        setFormDesc('');
        setFormConfig({});
        setTestResult(null);
        setShowForm(true);
    };

    const openEdit = async (p) => {
        try {
            const detail = await apiGet(`/api/authproviders/${p.id}`);
            if (!detail) return;
            setEditProvider(detail);
            setFormType(detail.auth_type);
            setFormName(detail.name);
            setFormDesc(detail.description || '');
            setFormConfig(detail.config || {});
            setTestResult(null);
            setShowForm(true);
        } catch (e) {
            toast.error('Failed to load provider');
        }
    };

    const handleTypeChange = (newType) => {
        setFormType(newType);
        // Preserve config if editing, reset if new
        if (!editProvider) {
            const defaults = {};
            (typeSchemas[newType]?.fields || []).forEach(f => {
                if (f.default !== undefined) defaults[f.name] = f.default;
            });
            setFormConfig(defaults);
        }
    };

    const handleSave = async () => {
        if (!formName.trim()) { toast.warning('Name is required'); return; }
        setSaving(true);
        try {
            await apiPost('/api/authproviders/save', {
                id: editProvider?.id,
                name: formName,
                auth_type: formType,
                description: formDesc,
                config: formConfig,
            });
            toast.success(editProvider ? 'Provider updated' : 'Provider created');
            setShowForm(false);
            fetchProviders();
        } catch (e) {
            toast.error(e.message || 'Save failed');
        } finally {
            setSaving(false);
        }
    };

    const handleTest = async () => {
        setTesting(true);
        setTestResult(null);
        try {
            const res = await apiPost('/api/authproviders/test', {
                auth_type: formType,
                config: formConfig,
            });
            setTestResult(res);
            if (res?.ok) {
                toast.success('Connection successful');
            } else {
                toast.warning(res?.error || 'Test failed');
            }
        } catch (e) {
            setTestResult({ ok: false, error: e.message });
            toast.error(e.message || 'Test failed');
        } finally {
            setTesting(false);
        }
    };

    const handleDelete = async () => {
        if (!deleteTarget) return;
        try {
            await apiDelete(`/api/authproviders/${deleteTarget.id}`);
            toast.success('Provider deleted');
            setDeleteTarget(null);
            fetchProviders();
        } catch (e) {
            toast.error(e.message || 'Delete failed');
        }
    };

    const currentFields = typeSchemas[formType]?.fields || [];

    if (loading) return html`<${Spinner} size="lg" message="Loading..." />`;

    return html`
        <div>
            <div class="page-header">
                <div>
                    <h1 class="page-title">Auth Providers</h1>
                    <p class="page-subtitle">Manage authentication providers for load tests</p>
                </div>
                <button class="btn btn-primary" onClick=${openNew}>+ New Provider</button>
            </div>

            ${providers.length === 0 ? html`
                <div class="card">
                    <div class="empty-state">
                        <div class="empty-state-icon"><${Icon} name="lock" size=${32} /></div>
                        <div class="empty-state-title">No Auth Providers</div>
                        <div class="empty-state-description">Configure authentication providers to authenticate your load test requests.</div>
                        <button class="btn btn-primary" onClick=${openNew}>+ New Provider</button>
                    </div>
                </div>
            ` : html`
                <div class="search-bar">
                    <input class="form-input" placeholder="Search providers..."
                        value=${search} onInput=${(e) => setSearch(e.target.value)} />
                    <div class="filter-chips">
                        ${['', ...Object.keys(typeSchemas)].map(t => html`
                            <span key=${t} class="filter-chip ${filterType === t ? 'active' : ''}"
                                onClick=${() => setFilterType(filterType === t ? '' : t)}>
                                ${t ? (AUTH_TYPE_LABELS[t] || t) : 'All'}
                            </span>
                        `)}
                    </div>
                </div>
                ${(() => {
                    const filtered = providers.filter(p => {
                        const q = search.toLowerCase();
                        const matchSearch = !q || p.name.toLowerCase().includes(q) || (p.description || '').toLowerCase().includes(q);
                        const matchType = !filterType || p.auth_type === filterType;
                        return matchSearch && matchType;
                    });
                    if (filtered.length === 0) return html`<div class="card"><div class="empty-state" style="padding: var(--space-6);"><p class="text-muted">No providers match your filter.</p></div></div>`;
                    return html`
                <div class="table-container">
                    <table class="table">
                        <thead><tr>
                            <th>Name</th><th>Type</th><th>Description</th><th>Updated</th><th></th>
                        </tr></thead>
                        <tbody>
                            ${filtered.map(p => html`
                                <tr key=${p.id}>
                                    <td style="font-weight: 500;">${p.name}</td>
                                    <td><span class="badge">${AUTH_TYPE_LABELS[p.auth_type] || p.auth_type}</span></td>
                                    <td class="text-muted">${p.description || '—'}</td>
                                    <td class="text-muted" style="font-size: var(--font-size-xs);">
                                        ${p.updated_at ? (() => { const d = new Date(p.updated_at); return d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'}); })() : '—'}
                                    </td>
                                    <td>
                                        <div class="flex gap-2 justify-end">
                                            ${(p.auth_type || '').includes('oauth2') || p.auth_type === 'jwt_custom' ? html`
                                                <button class="btn btn-ghost btn-sm" title="Refresh token"
                                                    onClick=${async () => {
                                                        try {
                                                            await apiPost('/api/authproviders/' + p.id + '/refresh');
                                                            toast.success('Token refreshed');
                                                        } catch (e) { toast.error('Refresh failed: ' + (e.message || '')); }
                                                    }}><${Icon} name="refresh" size=${14} /></button>
                                            ` : ''}
                                            <button class="btn btn-ghost btn-sm" onClick=${() => openEdit(p)}><${Icon} name="edit" size=${14} /></button>
                                            <button class="btn btn-ghost btn-sm" onClick=${() => setDeleteTarget(p)}><${Icon} name="trash" size=${14} /></button>
                                        </div>
                                    </td>
                                </tr>
                            `)}
                        </tbody>
                    </table>
                </div>`;
                })()}
                <div class="text-muted mt-2" style="font-size: var(--font-size-xs);">${providers.length} provider${providers.length !== 1 ? 's' : ''}</div>
            `}

            <${Modal} isOpen=${showForm}
                title=${editProvider ? 'Edit Auth Provider' : 'New Auth Provider'}
                onClose=${() => setShowForm(false)} wide=${true}>
                <div>
                    <div class="form-row">
                        <div class="form-group">
                            <label class="form-label">Name *</label>
                            <input class="form-input" value=${formName}
                                onInput=${(e) => setFormName(e.target.value)}
                                placeholder="e.g., Staging OAuth" />
                        </div>
                        <div class="form-group">
                            <label class="form-label">Auth Type</label>
                            <select class="form-select" value=${formType}
                                onChange=${(e) => handleTypeChange(e.target.value)}>
                                ${Object.keys(typeSchemas).map(t => html`
                                    <option key=${t} value=${t}>${AUTH_TYPE_LABELS[t] || t}</option>
                                `)}
                            </select>
                        </div>
                    </div>

                    <div class="form-group">
                        <label class="form-label">Description</label>
                        <input class="form-input" value=${formDesc}
                            onInput=${(e) => setFormDesc(e.target.value)}
                            placeholder="Optional description" />
                    </div>

                    <div style="border-top: 1px solid var(--border-primary); margin: var(--space-4) 0; padding-top: var(--space-4);">
                        <h4 style="margin-bottom: var(--space-3); font-size: var(--font-size-sm); color: var(--text-secondary);">
                            Configuration Fields
                        </h4>
                        ${currentFields.map(field => html`
                            <div key=${field.name} class="form-group">
                                <label class="form-label">
                                    ${field.label}${field.required ? ' *' : ''}
                                </label>
                                <${FieldInput}
                                    field=${field}
                                    value=${formConfig[field.name]}
                                    onChange=${(v) => setFormConfig(c => ({ ...c, [field.name]: v }))}
                                />
                                ${field.help && html`
                                    <div class="text-muted" style="font-size: var(--font-size-xs); margin-top: 2px;">${field.help}</div>
                                `}
                            </div>
                        `)}
                    </div>

                    ${testResult && html`
                        <div class="card" style="margin-bottom: var(--space-3); background: ${testResult.ok ? 'var(--bg-success)' : 'var(--bg-error)'};">
                            <div style="font-weight: 500; color: ${testResult.ok ? 'var(--color-success)' : 'var(--color-error)'};">
                                ${testResult.ok ? html`<${Icon} name="check-circle" size=${14} style=${{marginRight: '4px'}} /> Connection successful` : html`<${Icon} name="alert-circle" size=${14} style=${{marginRight: '4px'}} /> ${testResult.error || 'Test failed'}`}
                            </div>
                            ${testResult.headers && html`
                                <div class="text-mono text-muted" style="font-size: var(--font-size-xs); margin-top: var(--space-2);">
                                    Headers: ${JSON.stringify(testResult.headers)}
                                </div>
                            `}
                        </div>
                    `}

                    <div class="flex justify-between mt-4">
                        <button class="btn btn-secondary" onClick=${handleTest} disabled=${testing}>
                            ${testing ? 'Testing...' : html`<${Icon} name="zap" size=${14} style=${{marginRight: '4px'}} /> Test Connection`}
                        </button>
                        <div class="flex gap-3">
                            <button class="btn btn-secondary" onClick=${() => setShowForm(false)}>Cancel</button>
                            <button class="btn btn-primary" onClick=${handleSave} disabled=${saving}>
                                ${saving ? 'Saving...' : 'Save'}
                            </button>
                        </div>
                    </div>
                </div>
            </${Modal}>

            <${ConfirmDialog}
                isOpen=${!!deleteTarget}
                title="Delete Auth Provider"
                message=${`Delete "${deleteTarget?.name}"? Existing test configs referencing this provider will need updating.`}
                onConfirm=${handleDelete}
                onCancel=${() => setDeleteTarget(null)}
                confirmLabel="Delete"
                danger=${true}
            />
        </div>
    `;
}
