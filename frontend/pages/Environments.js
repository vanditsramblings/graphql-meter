/**
 * Environments.js — CRUD list + modal form for environment profiles.
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

const html = htm.bind(h);

const EMPTY_ENV = { name: '', base_url: '', graphql_path: '/graphql', platform: 'cloud', description: '', headers: '{}' };

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

    useEffect(() => { fetchEnvs(); }, []);

    const openNew = () => {
        setEditEnv(null);
        setForm({ ...EMPTY_ENV });
        setShowForm(true);
    };

    const openEdit = (env) => {
        setEditEnv(env);
        setForm({
            name: env.name || '',
            base_url: env.base_url || '',
            graphql_path: env.graphql_path || '/graphql',
            platform: env.platform || 'cloud',
            description: env.description || '',
            headers: env.headers ? (typeof env.headers === 'string' ? env.headers : JSON.stringify(env.headers, null, 2)) : '{}',
        });
        setShowForm(true);
    };

    const handleSave = async () => {
        if (!form.name.trim() || !form.base_url.trim()) {
            toast.warning('Name and Base URL are required');
            return;
        }
        let headers = {};
        try {
            headers = JSON.parse(form.headers || '{}');
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
                description: form.description,
                headers: headers,
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

    if (loading) return html`<${Spinner} size="lg" message="Loading..." />`;

    return html`
        <div>
            <div class="page-header">
                <div>
                    <h1 class="page-title">Environments</h1>
                    <p class="page-subtitle">Manage target environment profiles</p>
                </div>
                <button class="btn btn-primary" onClick=${openNew}>+ New Environment</button>
            </div>

            ${envs.length === 0 ? html`
                <div class="card">
                    <div class="empty-state">
                        <div class="empty-state-icon">🌐</div>
                        <div class="empty-state-title">No Environments</div>
                        <div class="empty-state-description">Create environment profiles to quickly configure test targets.</div>
                        <button class="btn btn-primary" onClick=${openNew}>+ New Environment</button>
                    </div>
                </div>
            ` : html`
                <div class="table-container">
                    <table class="table">
                        <thead><tr>
                            <th>Name</th><th>URL</th><th>Platform</th><th>Description</th><th></th>
                        </tr></thead>
                        <tbody>
                            ${envs.map(e => html`
                                <tr key=${e.id}>
                                    <td style="font-weight: 500;">${e.name}</td>
                                    <td class="text-mono text-muted" style="font-size: var(--font-size-xs);">${e.base_url}</td>
                                    <td><span class="badge">${e.platform || 'cloud'}</span></td>
                                    <td class="text-muted">${e.description || '—'}</td>
                                    <td>
                                        <div class="flex gap-2 justify-end">
                                            <button class="btn btn-ghost btn-sm" onClick=${() => openEdit(e)}>✏️</button>
                                            <button class="btn btn-ghost btn-sm" onClick=${() => setDeleteTarget(e)}>🗑</button>
                                        </div>
                                    </td>
                                </tr>
                            `)}
                        </tbody>
                    </table>
                </div>
            `}

            <${Modal} isOpen=${showForm} title=${editEnv ? 'Edit Environment' : 'New Environment'}
                onClose=${() => setShowForm(false)}>
                <div>
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
                        <label class="form-label">Description</label>
                        <input class="form-input" value=${form.description}
                            onInput=${(e) => setForm(f => ({ ...f, description: e.target.value }))} />
                    </div>
                    <div class="form-group">
                        <label class="form-label">Extra Headers (JSON)</label>
                        <textarea class="form-textarea" rows="3" value=${form.headers}
                            onInput=${(e) => setForm(f => ({ ...f, headers: e.target.value }))}
                            placeholder='{"Authorization": "Bearer ..."}' />
                    </div>
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
