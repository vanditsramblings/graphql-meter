/**
 * Environments.js — CRUD for environment profiles with TLS/mTLS,
 * certificate management, auth provider linking, and custom headers.
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
import { Icon } from '../components/Icons.js';

const html = htm.bind(h);

const EMPTY_ENV = {
    name: '', base_url: '', graphql_path: '/graphql', platform: 'cloud',
    protocol: 'https', tls_mode: 'standard', cert_type: 'none',
    cert_data: '', key_data: '', cert_password: '', ca_cert_data: '',
    verify_ssl: true, headers_json: '{}', auth_provider_id: '',
    notes: '',
};

export function Environments() {
    const { hasFlag } = useAuth();
    const toast = useToast();
    const [envs, setEnvs] = useState([]);
    const [loading, setLoading] = useState(true);
    const [showForm, setShowForm] = useState(false);
    const [editEnv, setEditEnv] = useState(null);
    const [form, setForm] = useState({ ...EMPTY_ENV });
    const [saving, setSaving] = useState(false);
    const [deleteTarget, setDeleteTarget] = useState(null);
    const [authProviders, setAuthProviders] = useState([]);
    const [activeTab, setActiveTab] = useState('general');
    const [search, setSearch] = useState('');
    const [filterProtocol, setFilterProtocol] = useState('');

    const fetchEnvs = async () => {
        try {
            const res = await apiGet('/api/environments/list');
            setEnvs(res?.environments || []);
        } catch (e) {
            toast.error('Failed to load environments');
        } finally {
            setLoading(false);
        }
    };

    const fetchAuthProviders = async () => {
        try {
            const res = await apiGet('/api/authproviders/list');
            setAuthProviders(res?.providers || []);
        } catch {}
    };

    useEffect(() => {
        Promise.all([fetchEnvs(), fetchAuthProviders()]);
    }, []);

    const openNew = () => {
        setEditEnv(null);
        setForm({ ...EMPTY_ENV });
        setActiveTab('general');
        setShowForm(true);
    };

    const openEdit = (env) => {
        setEditEnv(env);
        setForm({
            name: env.name || '',
            base_url: env.base_url || '',
            graphql_path: env.graphql_path || '/graphql',
            platform: env.platform || 'cloud',
            protocol: env.protocol || 'https',
            tls_mode: env.tls_mode || 'standard',
            cert_type: env.cert_type || 'none',
            cert_data: env.cert_data || '',
            key_data: env.key_data || '',
            cert_password: '',
            ca_cert_data: env.ca_cert_data || '',
            verify_ssl: env.verify_ssl !== 0 && env.verify_ssl !== false,
            headers_json: env.headers_json || '{}',
            auth_provider_id: env.auth_provider_id || '',
            notes: env.notes || '',
        });
        setActiveTab('general');
        setShowForm(true);
    };

    const handleSave = async () => {
        if (!form.name.trim()) {
            toast.warning('Name is required');
            return;
        }
        if (!form.base_url.trim()) {
            toast.warning('Base URL is required');
            return;
        }
        try {
            JSON.parse(form.headers_json || '{}');
        } catch {
            toast.warning('Headers must be valid JSON');
            return;
        }
        setSaving(true);
        try {
            await apiPost('/api/environments/save', {
                id: editEnv?.id,
                name: form.name,
                base_url: form.base_url,
                graphql_path: form.graphql_path,
                platform: form.platform,
                protocol: form.protocol,
                tls_mode: form.tls_mode,
                cert_type: form.cert_type,
                cert_data: form.cert_data,
                key_data: form.key_data,
                cert_password: form.cert_password,
                ca_cert_data: form.ca_cert_data,
                verify_ssl: form.verify_ssl,
                headers_json: form.headers_json,
                auth_provider_id: form.auth_provider_id,
                notes: form.notes,
            });
            toast.success(editEnv ? 'Environment updated' : 'Environment created');
            setShowForm(false);
            fetchEnvs();
        } catch (e) {
            toast.error(e.message || 'Save failed');
        } finally {
            setSaving(false);
        }
    };

    const handleDelete = async () => {
        if (!deleteTarget) return;
        try {
            await apiDelete(`/api/environments/${deleteTarget.id}`);
            toast.success('Environment deleted');
            setDeleteTarget(null);
            fetchEnvs();
        } catch (e) {
            toast.error(e.message || 'Delete failed');
        }
    };

    const protocolBadge = (env) => {
        const p = env.protocol || 'https';
        const colors = { http: 'var(--status-warning)', https: 'var(--status-success)', mtls: 'var(--accent-secondary)' };
        return html`<span class="badge" style="background: ${colors[p] || colors.https}22; color: ${colors[p] || colors.https}; border: 1px solid ${colors[p] || colors.https}44;">${p.toUpperCase()}</span>`;
    };

    const tlsBadge = (env) => {
        const t = env.tls_mode || 'standard';
        if (t === 'mtls') return html`<span class="badge" style="background: var(--accent-secondary)22; color: var(--accent-secondary);">mTLS</span>`;
        if (t === 'standard') return html`<span class="badge" style="background: var(--status-success)22; color: var(--status-success);">TLS</span>`;
        return html`<span class="badge text-muted">None</span>`;
    };

    if (loading) return html`<${Spinner} size="lg" message="Loading..." />`;

    const tabs = ['general', 'security', 'headers'];

    return html`
        <div>
            <div class="page-header">
                <div>
                    <h1 class="page-title">Environments</h1>
                    <p class="page-subtitle">Manage target environments with TLS, certificates, and auth providers</p>
                </div>
                <button class="btn btn-primary" onClick=${openNew}>+ New Environment</button>
            </div>

            ${envs.length === 0 ? html`
                <div class="card">
                    <div class="empty-state">
                        <div class="empty-state-icon"><${Icon} name="globe" size=${32} /></div>
                        <div class="empty-state-title">No Environments</div>
                        <div class="empty-state-description">Create environment profiles to define target hosts with security configurations.</div>
                        <button class="btn btn-primary" onClick=${openNew}>+ New Environment</button>
                    </div>
                </div>
            ` : html`
                <div class="search-bar">
                    <input class="form-input" placeholder="Search environments..."
                        value=${search} onInput=${(e) => setSearch(e.target.value)} />
                    <div class="filter-chips">
                        ${['', 'http', 'https', 'mtls'].map(p => html`
                            <span key=${p} class="filter-chip ${filterProtocol === p ? 'active' : ''}"
                                onClick=${() => setFilterProtocol(filterProtocol === p ? '' : p)}>
                                ${p || 'All'}
                            </span>
                        `)}
                    </div>
                </div>
                ${(() => {
                    const filtered = envs.filter(e => {
                        const q = search.toLowerCase();
                        const matchSearch = !q || e.name.toLowerCase().includes(q) || (e.base_url || '').toLowerCase().includes(q);
                        const matchProto = !filterProtocol || (e.protocol || 'https') === filterProtocol;
                        return matchSearch && matchProto;
                    });
                    if (filtered.length === 0) return html`<div class="card"><div class="empty-state" style="padding: var(--space-6);"><p class="text-muted">No environments match your filter.</p></div></div>`;
                    return html`
                <div class="table-container">
                    <table class="table">
                        <thead><tr>
                            <th>Name</th><th>URL</th><th>Protocol</th><th>TLS</th><th>Auth</th><th>Platform</th><th></th>
                        </tr></thead>
                        <tbody>
                            ${filtered.map(e => html`
                                <tr key=${e.id}>
                                    <td style="font-weight: 500;">${e.name}</td>
                                    <td class="text-mono text-muted" style="font-size: var(--font-size-xs);">${e.base_url}${e.graphql_path || ''}</td>
                                    <td>${protocolBadge(e)}</td>
                                    <td>${tlsBadge(e)}</td>
                                    <td>${e.auth_provider_id ? html`<span class="badge" style="background: var(--accent-primary)22; color: var(--accent-primary);"><${Icon} name="key" size=${12} style=${{marginRight: '4px'}} /> Linked</span>` : html`<span class="text-muted">—</span>`}</td>
                                    <td><span class="badge">${e.platform || 'cloud'}</span></td>
                                    <td>
                                        <div class="flex gap-2 justify-end">
                                            <button class="btn btn-ghost btn-sm" onClick=${() => openEdit(e)}><${Icon} name="edit" size=${14} /></button>
                                            <button class="btn btn-ghost btn-sm" onClick=${() => setDeleteTarget(e)}><${Icon} name="trash" size=${14} /></button>
                                        </div>
                                    </td>
                                </tr>
                            `)}
                        </tbody>
                    </table>
                </div>`;
                })()}
                <div class="text-muted mt-2" style="font-size: var(--font-size-xs);">${envs.length} environment${envs.length !== 1 ? 's' : ''}</div>
            `}

            <${Modal} isOpen=${showForm} title=${editEnv ? 'Edit Environment' : 'New Environment'}
                onClose=${() => setShowForm(false)} width="700px">
                <div>
                    <!-- Tabs -->
                    <div class="flex gap-2 mb-4" style="border-bottom: 1px solid var(--border-weak); padding-bottom: 8px;">
                        ${tabs.map(t => html`
                            <button key=${t} class=${'btn btn-sm ' + (activeTab === t ? 'btn-primary' : 'btn-ghost')}
                                onClick=${() => setActiveTab(t)}>${t.charAt(0).toUpperCase() + t.slice(1)}</button>
                        `)}
                    </div>

                    ${activeTab === 'general' && html`
                        <div class="form-group">
                            <label class="form-label">Name *</label>
                            <input class="form-input" value=${form.name}
                                onInput=${(e) => setForm(f => ({ ...f, name: e.target.value }))} placeholder="e.g., Staging" />
                        </div>
                        <div class="form-group">
                            <label class="form-label">Base URL *</label>
                            <input class="form-input" value=${form.base_url}
                                onInput=${(e) => setForm(f => ({ ...f, base_url: e.target.value }))} placeholder="https://api-staging.example.com" />
                        </div>
                        <div class="form-row">
                            <div class="form-group">
                                <label class="form-label">GraphQL Path</label>
                                <input class="form-input" value=${form.graphql_path}
                                    onInput=${(e) => setForm(f => ({ ...f, graphql_path: e.target.value }))} />
                            </div>
                            <div class="form-group">
                                <label class="form-label">Platform</label>
                                <select class="form-select" value=${form.platform}
                                    onChange=${(e) => setForm(f => ({ ...f, platform: e.target.value }))}>
                                    <option value="cloud">Cloud</option>
                                    <option value="onprem">On-Premises</option>
                                </select>
                            </div>
                        </div>
                        <div class="form-group">
                            <label class="form-label">Auth Provider</label>
                            <select class="form-select" value=${form.auth_provider_id}
                                onChange=${(e) => setForm(f => ({ ...f, auth_provider_id: e.target.value }))}>
                                <option value="">— None —</option>
                                ${authProviders.map(p => html`<option key=${p.id} value=${p.id}>${p.name} (${p.auth_type})</option>`)}
                            </select>
                            <span class="form-help">Link an authentication provider for automatic header injection</span>
                        </div>
                        <div class="form-group">
                            <label class="form-label">Notes</label>
                            <textarea class="form-textarea" rows="2" value=${form.notes}
                                onInput=${(e) => setForm(f => ({ ...f, notes: e.target.value }))} placeholder="Description or notes..." />
                        </div>
                    `}

                    ${activeTab === 'security' && html`
                        <div class="form-row">
                            <div class="form-group">
                                <label class="form-label">Protocol</label>
                                <select class="form-select" value=${form.protocol}
                                    onChange=${(e) => {
                                        const proto = e.target.value;
                                        setForm(f => ({
                                            ...f, protocol: proto,
                                            tls_mode: proto === 'http' ? 'none' : proto === 'mtls' ? 'mtls' : 'standard',
                                        }));
                                    }}>
                                    <option value="http">HTTP</option>
                                    <option value="https">HTTPS</option>
                                    <option value="mtls">mTLS</option>
                                </select>
                            </div>
                            <div class="form-group">
                                <label class="form-label">TLS Mode</label>
                                <select class="form-select" value=${form.tls_mode}
                                    onChange=${(e) => setForm(f => ({ ...f, tls_mode: e.target.value }))}>
                                    <option value="none">No TLS</option>
                                    <option value="standard">Standard TLS</option>
                                    <option value="mtls">Mutual TLS (mTLS)</option>
                                </select>
                            </div>
                        </div>
                        <div class="form-group">
                            <label class="form-label" style="display: flex; align-items: center; gap: 8px;">
                                <input type="checkbox" checked=${form.verify_ssl}
                                    onChange=${(e) => setForm(f => ({ ...f, verify_ssl: e.target.checked }))} />
                                Verify SSL Certificate
                            </label>
                            <span class="form-help">Disable for self-signed certificates (not recommended for production)</span>
                        </div>

                        ${(form.tls_mode === 'mtls' || form.protocol === 'mtls') && html`
                            <div style="border: 1px solid var(--border-weak); border-radius: var(--radius-md); padding: 16px; margin-top: 12px;">
                                <h4 style="margin: 0 0 12px 0; color: var(--text-primary);">Client Certificate</h4>
                                <div class="form-group">
                                    <label class="form-label">Certificate Type</label>
                                    <select class="form-select" value=${form.cert_type}
                                        onChange=${(e) => setForm(f => ({ ...f, cert_type: e.target.value }))}>
                                        <option value="none">None</option>
                                        <option value="pem">PEM (Certificate + Key files)</option>
                                        <option value="pfx">PFX / PKCS#12</option>
                                        <option value="cert_key">Base64 (Copy-paste)</option>
                                    </select>
                                </div>

                                ${form.cert_type === 'pem' && html`
                                    <div class="form-group">
                                        <label class="form-label">Certificate (PEM)</label>
                                        <textarea class="form-textarea text-mono" rows="4" value=${form.cert_data}
                                            onInput=${(e) => setForm(f => ({ ...f, cert_data: e.target.value }))}
                                            placeholder="-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----" />
                                        <input type="file" accept=".pem,.crt,.cer" style="margin-top: 4px; font-size: var(--font-size-xs);"
                                            onChange=${(e) => { const f = e.target.files[0]; if (f) { const r = new FileReader(); r.onload = () => setForm(fm => ({ ...fm, cert_data: r.result })); r.readAsText(f); } }} />
                                    </div>
                                    <div class="form-group">
                                        <label class="form-label">Private Key (PEM)</label>
                                        <textarea class="form-textarea text-mono" rows="4" value=${form.key_data}
                                            onInput=${(e) => setForm(f => ({ ...f, key_data: e.target.value }))}
                                            placeholder="-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----" />
                                        <input type="file" accept=".pem,.key" style="margin-top: 4px; font-size: var(--font-size-xs);"
                                            onChange=${(e) => { const f = e.target.files[0]; if (f) { const r = new FileReader(); r.onload = () => setForm(fm => ({ ...fm, key_data: r.result })); r.readAsText(f); } }} />
                                    </div>
                                    <div class="form-group">
                                        <label class="form-label">Key Password (if encrypted)</label>
                                        <input type="password" class="form-input" value=${form.cert_password}
                                            onInput=${(e) => setForm(f => ({ ...f, cert_password: e.target.value }))} />
                                    </div>
                                `}

                                ${form.cert_type === 'pfx' && html`
                                    <div class="form-group">
                                        <label class="form-label">PFX File (Base64)</label>
                                        <textarea class="form-textarea text-mono" rows="4" value=${form.cert_data}
                                            onInput=${(e) => setForm(f => ({ ...f, cert_data: e.target.value }))}
                                            placeholder="Base64-encoded PFX content" />
                                        <input type="file" accept=".pfx,.p12" style="margin-top: 4px; font-size: var(--font-size-xs);"
                                            onChange=${(e) => { const f = e.target.files[0]; if (f) { const r = new FileReader(); r.onload = () => { const b64 = r.result.split(',')[1]; setForm(fm => ({ ...fm, cert_data: b64 })); }; r.readAsDataURL(f); } }} />
                                        <span class="form-help">Upload a PFX file or paste base64-encoded content</span>
                                    </div>
                                    <div class="form-group">
                                        <label class="form-label">PFX Password *</label>
                                        <input type="password" class="form-input" value=${form.cert_password}
                                            onInput=${(e) => setForm(f => ({ ...f, cert_password: e.target.value }))}
                                            placeholder="PFX password" />
                                    </div>
                                `}

                                ${form.cert_type === 'cert_key' && html`
                                    <div class="form-group">
                                        <label class="form-label">Certificate (Base64)</label>
                                        <textarea class="form-textarea text-mono" rows="3" value=${form.cert_data}
                                            onInput=${(e) => setForm(f => ({ ...f, cert_data: e.target.value }))} />
                                    </div>
                                    <div class="form-group">
                                        <label class="form-label">Private Key (Base64)</label>
                                        <textarea class="form-textarea text-mono" rows="3" value=${form.key_data}
                                            onInput=${(e) => setForm(f => ({ ...f, key_data: e.target.value }))} />
                                    </div>
                                    <div class="form-group">
                                        <label class="form-label">Key Password</label>
                                        <input type="password" class="form-input" value=${form.cert_password}
                                            onInput=${(e) => setForm(f => ({ ...f, cert_password: e.target.value }))} />
                                    </div>
                                `}

                                <div class="form-group">
                                    <label class="form-label">CA Certificate (optional)</label>
                                    <textarea class="form-textarea text-mono" rows="3" value=${form.ca_cert_data}
                                        onInput=${(e) => setForm(f => ({ ...f, ca_cert_data: e.target.value }))}
                                        placeholder="CA bundle for custom certificate authorities" />
                                    <input type="file" accept=".pem,.crt,.cer" style="margin-top: 4px; font-size: var(--font-size-xs);"
                                        onChange=${(e) => { const f = e.target.files[0]; if (f) { const r = new FileReader(); r.onload = () => setForm(fm => ({ ...fm, ca_cert_data: r.result })); r.readAsText(f); } }} />
                                </div>
                            </div>
                        `}
                    `}

                    ${activeTab === 'headers' && html`
                        <div class="form-group">
                            <label class="form-label">Custom Headers (JSON)</label>
                            <textarea class="form-textarea text-mono" rows="8" value=${form.headers_json}
                                onInput=${(e) => setForm(f => ({ ...f, headers_json: e.target.value }))}
                                placeholder='{\n  "X-Custom-Header": "value",\n  "Accept": "application/json"\n}' />
                            <span class="form-help">These headers will be sent with every request to this environment</span>
                        </div>
                    `}

                    <div class="flex justify-end gap-3 mt-4">
                        <button class="btn btn-secondary" onClick=${() => setShowForm(false)}>Cancel</button>
                        <button class="btn btn-primary" onClick=${handleSave} disabled=${saving}>
                            ${saving ? 'Saving...' : 'Save'}
                        </button>
                    </div>
                </div>
            </${Modal}>

            <${ConfirmDialog}
                isOpen=${!!deleteTarget}
                title="Delete Environment"
                message=${`Delete "${deleteTarget?.name}"? This cannot be undone.`}
                onConfirm=${handleDelete}
                onCancel=${() => setDeleteTarget(null)}
                confirmLabel="Delete"
                danger=${true}
            />
        </div>
    `;
}
