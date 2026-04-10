/**
 * GraphQLClient.js — Built-in GraphQL client for query execution and verification.
 *
 * Features:
 * - Execute queries/mutations against any environment
 * - Import operations from test configs
 * - Save and manage reusable requests
 * - Introspection support
 * - Syntax-highlighted response viewer
 */
import { h } from 'preact';
import { useState, useEffect } from 'preact/hooks';
import htm from 'htm';
import { apiGet, apiPost, apiDelete } from '../lib/api.js';
import { useAuth } from '../lib/auth.js';
import { Icon } from '../components/Icons.js';
import { useToast } from '../components/Toast.js';
import { Spinner } from '../components/Spinner.js';
import { Modal } from '../components/Modal.js';
import { ConfirmDialog } from '../components/ConfirmDialog.js';

const html = htm.bind(h);

const DEFAULT_QUERY = `# Write your GraphQL query here
query {
  __typename
}`;

export function GraphQLClient() {
    const { hasFlag } = useAuth();
    const toast = useToast();

    // State
    const [query, setQuery] = useState(DEFAULT_QUERY);
    const [variables, setVariables] = useState('{}');
    const [operationName, setOperationName] = useState('');
    const [response, setResponse] = useState(null);
    const [executing, setExecuting] = useState(false);
    const [environments, setEnvironments] = useState([]);
    const [authProviders, setAuthProviders] = useState([]);
    const [selectedEnvId, setSelectedEnvId] = useState('');
    const [selectedAuthId, setSelectedAuthId] = useState('');
    const [directUrl, setDirectUrl] = useState('');
    const [customHeaders, setCustomHeaders] = useState('{}');
    const [timeoutSec, setTimeoutSec] = useState(30);

    // Saved requests
    const [savedRequests, setSavedRequests] = useState([]);
    const [showSaved, setShowSaved] = useState(false);
    const [saveName, setSaveName] = useState('');
    const [showSaveModal, setShowSaveModal] = useState(false);
    const [editRequestId, setEditRequestId] = useState(null);
    const [deleteTarget, setDeleteTarget] = useState(null);

    // Import from config
    const [configs, setConfigs] = useState([]);
    const [showImport, setShowImport] = useState(false);
    const [importOps, setImportOps] = useState([]);
    const [importConfigName, setImportConfigName] = useState('');

    // Panel sizes
    const [activePanel, setActivePanel] = useState('response');
    const [collectionOpen, setCollectionOpen] = useState(true);

    const fetchData = async () => {
        try {
            const [envRes, authRes, reqRes, cfgRes] = await Promise.all([
                apiGet('/api/environments/list'),
                apiGet('/api/authproviders/list'),
                apiGet('/api/graphqlclient/requests/list'),
                apiGet('/api/testconfig/list'),
            ]);
            setEnvironments(envRes?.environments || []);
            setAuthProviders(authRes?.providers || []);
            setSavedRequests(reqRes?.requests || []);
            setConfigs(cfgRes?.configs || []);
        } catch (e) {
            toast.error('Failed to load data');
        }
    };

    useEffect(() => { fetchData(); }, []);

    const handleExecute = async () => {
        if (!query.trim()) {
            toast.warning('Query is required');
            return;
        }

        let vars = {};
        try {
            vars = JSON.parse(variables || '{}');
        } catch {
            toast.warning('Variables must be valid JSON');
            return;
        }

        let hdrs = {};
        try {
            hdrs = JSON.parse(customHeaders || '{}');
        } catch {
            toast.warning('Headers must be valid JSON');
            return;
        }

        setExecuting(true);
        setResponse(null);
        try {
            const res = await apiPost('/api/graphqlclient/execute', {
                query: query,
                variables: vars,
                operation_name: operationName,
                environment_id: selectedEnvId,
                auth_provider_id: selectedAuthId,
                target_url: directUrl,
                headers: hdrs,
                timeout_sec: timeoutSec,
            });
            setResponse(res);
            setActivePanel('response');
        } catch (e) {
            setResponse({ success: false, error: e.message || 'Execution failed' });
        } finally {
            setExecuting(false);
        }
    };

    const handleIntrospect = async () => {
        let hdrs = {};
        try {
            hdrs = JSON.parse(customHeaders || '{}');
        } catch {
            toast.warning('Headers must be valid JSON');
            return;
        }
        setExecuting(true);
        setResponse(null);
        try {
            const res = await apiPost('/api/graphqlclient/introspect', {
                environment_id: selectedEnvId,
                target_url: directUrl,
                auth_provider_id: selectedAuthId,
                headers: hdrs,
            });
            if (res?.success) {
                toast.success(`Found ${res.query_count} queries and ${res.mutation_count} mutations`);
                setResponse(res);
                setActivePanel('response');
            } else {
                toast.error(res?.error || 'Introspection failed');
                setResponse(res);
            }
        } catch (e) {
            toast.error(e.message || 'Introspection failed');
        } finally {
            setExecuting(false);
        }
    };

    const handleSaveRequest = async () => {
        if (!saveName.trim()) {
            toast.warning('Name is required');
            return;
        }
        try {
            await apiPost('/api/graphqlclient/requests/save', {
                id: editRequestId,
                name: saveName,
                query: query,
                variables_json: variables,
                headers_json: customHeaders,
                environment_id: selectedEnvId,
                auth_provider_id: selectedAuthId,
                operation_name: operationName,
            });
            toast.success(editRequestId ? 'Request updated' : 'Request saved');
            setShowSaveModal(false);
            setSaveName('');
            setEditRequestId(null);
            fetchData();
        } catch (e) {
            toast.error(e.message || 'Save failed');
        }
    };

    const loadSavedRequest = async (reqId) => {
        try {
            const res = await apiGet(`/api/graphqlclient/requests/${reqId}`);
            setQuery(res.query || '');
            setVariables(typeof res.variables_json === 'object' ? JSON.stringify(res.variables_json, null, 2) : (res.variables_json || '{}'));
            setCustomHeaders(typeof res.headers_json === 'object' ? JSON.stringify(res.headers_json, null, 2) : (res.headers_json || '{}'));
            setSelectedEnvId(res.environment_id || '');
            setSelectedAuthId(res.auth_provider_id || '');
            setOperationName(res.operation_name || '');
            setEditRequestId(res.id);
            setSaveName(res.name);
            setShowSaved(false);
            toast.success(`Loaded: ${res.name}`);
        } catch (e) {
            toast.error('Failed to load request');
        }
    };

    const handleImportFromConfig = async (configId) => {
        try {
            const res = await apiGet(`/api/graphqlclient/from-config/${configId}`);
            setImportOps(res?.operations || []);
            setImportConfigName(res?.config_name || '');
            if (res?.global_params?.host) {
                setDirectUrl(res.global_params.host + (res.global_params.graphql_path || '/graphql'));
            }
        } catch (e) {
            toast.error('Failed to load config operations');
        }
    };

    const selectImportOp = (op) => {
        setQuery(op.query || `${op.type} { ${op.name} }`);
        setVariables(JSON.stringify(op.variables || {}, null, 2));
        setOperationName(op.name);
        setShowImport(false);
        toast.success(`Imported: ${op.name}`);
    };

    const handleDeleteRequest = async () => {
        if (!deleteTarget) return;
        try {
            await apiDelete(`/api/graphqlclient/requests/${deleteTarget.id}`);
            toast.success('Request deleted');
            setDeleteTarget(null);
            fetchData();
        } catch (e) {
            toast.error(e.message || 'Delete failed');
        }
    };

    const selectedEnv = environments.find(e => e.id === selectedEnvId);
    const targetDisplay = selectedEnv
        ? `${selectedEnv.name}: ${selectedEnv.base_url}${selectedEnv.graphql_path || '/graphql'}`
        : (directUrl || 'No target selected');

    return html`
        <div style="display: flex; flex-direction: column; height: calc(100vh - 80px);">
            <!-- Header -->
            <div class="page-header" style="flex-shrink: 0;">
                <div>
                    <h1 class="page-title">GraphQL Client</h1>
                    <p class="page-subtitle">Execute and verify GraphQL queries before load testing</p>
                </div>
                <div class="flex gap-2">
                    <button class="btn btn-ghost btn-sm" onClick=${() => setCollectionOpen(!collectionOpen)} title="Toggle collection">
                        <${Icon} name=${collectionOpen ? 'sidebar-close' : 'sidebar-open'} size=${14} style=${{marginRight: '4px'}} /> Collection
                    </button>
                    <button class="btn btn-ghost btn-sm" onClick=${() => setShowImport(true)}><${Icon} name="download" size=${14} style=${{marginRight: '4px'}} /> Import</button>
                    <button class="btn btn-ghost btn-sm" onClick=${() => { setShowSaveModal(true); if (!saveName) setSaveName(''); }}><${Icon} name="save" size=${14} style=${{marginRight: '4px'}} /> Save</button>
                </div>
            </div>

            <!-- Target Configuration Bar -->
            <div style="flex-shrink: 0; padding: 8px 0; display: flex; gap: 8px; flex-wrap: wrap; align-items: end;">
                <div style="flex: 1; min-width: 200px;">
                    <label class="form-label" style="font-size: 11px; margin-bottom: 2px;">Environment</label>
                    <select class="form-select" value=${selectedEnvId}
                        onChange=${(e) => { setSelectedEnvId(e.target.value); if (e.target.value) setDirectUrl(''); }}>
                        <option value="">— Direct URL —</option>
                        ${environments.map(e => html`<option key=${e.id} value=${e.id}>${e.name} (${e.protocol || 'https'})</option>`)}
                    </select>
                </div>
                ${!selectedEnvId && html`
                    <div style="flex: 2; min-width: 250px;">
                        <label class="form-label" style="font-size: 11px; margin-bottom: 2px;">Target URL</label>
                        <input class="form-input" value=${directUrl}
                            onInput=${(e) => setDirectUrl(e.target.value)}
                            placeholder="https://api.example.com/graphql" />
                    </div>
                `}
                <div style="min-width: 180px;">
                    <label class="form-label" style="font-size: 11px; margin-bottom: 2px;">Auth Provider</label>
                    <select class="form-select" value=${selectedAuthId}
                        onChange=${(e) => setSelectedAuthId(e.target.value)}>
                        <option value="">— None —</option>
                        ${authProviders.map(p => html`<option key=${p.id} value=${p.id}>${p.name}</option>`)}
                    </select>
                </div>
                <button class="btn btn-primary" onClick=${handleExecute} disabled=${executing}
                    style="height: 36px;">
                    ${executing ? 'Running...' : html`<${Icon} name="play" size=${14} style=${{marginRight: '4px'}} /> Execute`}
                </button>
                <button class="btn btn-secondary btn-sm" onClick=${handleIntrospect} disabled=${executing}
                    style="height: 36px;" title="Run introspection query">
                    <${Icon} name="search" size=${14} style=${{marginRight: '4px'}} /> Introspect
                </button>
            </div>

            <!-- Main Content: Collection + Editor + Response -->
            <div style="flex: 1; display: flex; gap: 0; min-height: 0; overflow: hidden;">
                <!-- Collection Sidebar -->
                ${collectionOpen && html`
                    <div class="collection-panel" style="width: 240px; flex-shrink: 0; border-right: 1px solid var(--border-primary); display: flex; flex-direction: column; overflow: hidden;">
                        <div class="collection-header" style="padding: 8px 12px; border-bottom: 1px solid var(--border-weak); display: flex; justify-content: space-between; align-items: center;">
                            <span style="font-weight: 600; font-size: var(--font-size-sm);"><${Icon} name="folder" size=${14} style=${{marginRight: '4px'}} /> Collection</span>
                            <span class="text-muted" style="font-size: var(--font-size-xs);">${savedRequests.length}</span>
                        </div>
                        <div class="collection-tree" style="flex: 1; overflow-y: auto; padding: 4px 0;">
                            ${(() => {
                                const queries = savedRequests.filter(r => !(r.query || '').trimStart().startsWith('mutation'));
                                const mutations = savedRequests.filter(r => (r.query || '').trimStart().startsWith('mutation'));
                                return html`
                                    ${queries.length > 0 && html`
                                        <div class="collection-group">
                                            <div style="padding: 4px 12px; font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-disabled); font-weight: 600;">Queries</div>
                                            ${queries.map(r => html`
                                                <div key=${r.id} class="collection-item" style="padding: 6px 12px 6px 20px; cursor: pointer; display: flex; align-items: center; gap: 6px; font-size: var(--font-size-xs); border-left: 2px solid transparent;"
                                                    onClick=${() => loadSavedRequest(r.id)}
                                                    onMouseOver=${(e) => e.currentTarget.style.background = 'var(--bg-tertiary)'}
                                                    onMouseOut=${(e) => e.currentTarget.style.background = 'transparent'}>
                                                    <span class="method-query" style="color: var(--color-info); font-weight: 600; font-size: 10px; min-width: 14px;">Q</span>
                                                    <span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title=${r.name}>${r.name}</span>
                                                </div>
                                            `)}
                                        </div>
                                    `}
                                    ${mutations.length > 0 && html`
                                        <div class="collection-group">
                                            <div style="padding: 4px 12px; font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-disabled); font-weight: 600; margin-top: 8px;">Mutations</div>
                                            ${mutations.map(r => html`
                                                <div key=${r.id} class="collection-item" style="padding: 6px 12px 6px 20px; cursor: pointer; display: flex; align-items: center; gap: 6px; font-size: var(--font-size-xs); border-left: 2px solid transparent;"
                                                    onClick=${() => loadSavedRequest(r.id)}
                                                    onMouseOver=${(e) => e.currentTarget.style.background = 'var(--bg-tertiary)'}
                                                    onMouseOut=${(e) => e.currentTarget.style.background = 'transparent'}>
                                                    <span class="method-mutation" style="color: var(--color-warning); font-weight: 600; font-size: 10px; min-width: 14px;">M</span>
                                                    <span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title=${r.name}>${r.name}</span>
                                                </div>
                                            `)}
                                        </div>
                                    `}
                                    ${savedRequests.length === 0 && html`
                                        <div class="text-muted" style="padding: 20px 12px; text-align: center; font-size: var(--font-size-xs);">
                                            No saved requests yet. Save a query to see it here.
                                        </div>
                                    `}
                                `;
                            })()}
                        </div>
                    </div>
                `}

                <!-- Editor + Response area -->
                <div style="flex: 1; display: flex; gap: 12px; min-height: 0; overflow: hidden; padding-left: ${collectionOpen ? '12px' : '0'};">
                <!-- Left: Query Editor -->
                <div style="flex: 1; display: flex; flex-direction: column; min-width: 0;">
                    <div style="flex: 1; display: flex; flex-direction: column;">
                        <label class="form-label" style="font-size: 11px; margin-bottom: 4px;">Query</label>
                        <textarea class="form-textarea text-mono"
                            style="flex: 1; resize: none; font-size: 13px; line-height: 1.5; background: var(--bg-primary); border-color: var(--border-weak);"
                            value=${query}
                            onInput=${(e) => setQuery(e.target.value)}
                            placeholder="Enter your GraphQL query..." />
                    </div>

                    <!-- Bottom panels: Variables / Headers / Settings -->
                    <div style="margin-top: 8px;">
                        <div class="flex gap-2" style="margin-bottom: 4px;">
                            ${['variables', 'headers', 'settings'].map(p => html`
                                <button key=${p} class=${'btn btn-sm ' + (activePanel === p ? 'btn-primary' : 'btn-ghost')}
                                    onClick=${() => setActivePanel(p)}>${p.charAt(0).toUpperCase() + p.slice(1)}</button>
                            `)}
                        </div>
                        ${activePanel === 'variables' && html`
                            <textarea class="form-textarea text-mono" rows="4"
                                style="font-size: 12px; background: var(--bg-primary);"
                                value=${variables}
                                onInput=${(e) => setVariables(e.target.value)}
                                placeholder='{ "key": "value" }' />
                        `}
                        ${activePanel === 'headers' && html`
                            <textarea class="form-textarea text-mono" rows="4"
                                style="font-size: 12px; background: var(--bg-primary);"
                                value=${customHeaders}
                                onInput=${(e) => setCustomHeaders(e.target.value)}
                                placeholder='{ "X-Custom": "value" }' />
                        `}
                        ${activePanel === 'settings' && html`
                            <div class="card" style="padding: 12px;">
                                <div class="form-row">
                                    <div class="form-group" style="flex: 1;">
                                        <label class="form-label" style="font-size: 11px;">Operation Name</label>
                                        <input class="form-input" value=${operationName}
                                            onInput=${(e) => setOperationName(e.target.value)}
                                            placeholder="optional" />
                                    </div>
                                    <div class="form-group" style="width: 120px;">
                                        <label class="form-label" style="font-size: 11px;">Timeout (sec)</label>
                                        <input class="form-input" type="number" value=${timeoutSec}
                                            onInput=${(e) => setTimeoutSec(parseInt(e.target.value) || 30)} />
                                    </div>
                                </div>
                            </div>
                        `}
                    </div>
                </div>

                <!-- Right: Response -->
                <div style="flex: 1; display: flex; flex-direction: column; min-width: 0;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                        <label class="form-label" style="font-size: 11px; margin: 0;">Response</label>
                        ${response && html`
                            <div class="flex gap-2" style="font-size: 11px;">
                                <span style="color: ${response.success ? 'var(--status-success)' : 'var(--status-error)'};">
                                    ${response.status_code ? `HTTP ${response.status_code}` : ''}
                                </span>
                                ${response.elapsed_ms != null && html`
                                    <span class="text-muted">${response.elapsed_ms}ms</span>
                                `}
                            </div>
                        `}
                    </div>
                    <div style="flex: 1; overflow: auto; background: var(--bg-primary); border: 1px solid var(--border-weak); border-radius: var(--radius-md); padding: 12px;">
                        ${!response && !executing && html`
                            <div style="color: var(--text-disabled); text-align: center; padding-top: 40px;">
                                Click Execute to run your query
                            </div>
                        `}
                        ${executing && html`<${Spinner} size="sm" message="Executing..." />`}
                        ${response && html`
                            <pre class="text-mono" style="font-size: 12px; line-height: 1.5; color: var(--text-primary); white-space: pre-wrap; word-break: break-word; margin: 0;">
${response.error
    ? response.error
    : JSON.stringify(response.response || response, null, 2)}
                            </pre>
                        `}
                    </div>
                    ${response?.response_headers && html`
                        <details style="margin-top: 8px;">
                            <summary class="text-muted" style="font-size: 11px; cursor: pointer;">Response Headers</summary>
                            <pre class="text-mono" style="font-size: 11px; color: var(--text-secondary); margin-top: 4px;">
${JSON.stringify(response.response_headers, null, 2)}
                            </pre>
                        </details>
                    `}
                </div>
            </div>
            </div>

            <!-- Saved Requests Modal -->
            <${Modal} isOpen=${showSaved} title="Saved Requests" onClose=${() => setShowSaved(false)} width="600px">
                <div>
                    ${savedRequests.length === 0 ? html`
                        <div class="text-muted" style="text-align: center; padding: 20px;">No saved requests yet</div>
                    ` : html`
                        <div class="table-container">
                            <table class="table">
                                <thead><tr><th>Name</th><th>Environment</th><th></th></tr></thead>
                                <tbody>
                                    ${savedRequests.map(r => html`
                                        <tr key=${r.id}>
                                            <td style="font-weight: 500; cursor: pointer;" onClick=${() => loadSavedRequest(r.id)}>${r.name}</td>
                                            <td class="text-muted">${environments.find(e => e.id === r.environment_id)?.name || '—'}</td>
                                            <td>
                                                <div class="flex gap-2 justify-end">
                                                    <button class="btn btn-ghost btn-sm" onClick=${() => loadSavedRequest(r.id)}><${Icon} name="folder-open" size=${14} /></button>
                                                    <button class="btn btn-ghost btn-sm" onClick=${() => setDeleteTarget(r)}><${Icon} name="trash" size=${14} /></button>
                                                </div>
                                            </td>
                                        </tr>
                                    `)}
                                </tbody>
                            </table>
                        </div>
                    `}
                </div>
            </${Modal}>

            <!-- Save Request Modal -->
            <${Modal} isOpen=${showSaveModal} title=${editRequestId ? 'Update Request' : 'Save Request'} onClose=${() => setShowSaveModal(false)}>
                <div>
                    <div class="form-group">
                        <label class="form-label">Name *</label>
                        <input class="form-input" value=${saveName}
                            onInput=${(e) => setSaveName(e.target.value)}
                            placeholder="e.g., Get Users Query" />
                    </div>
                    <div class="flex justify-end gap-3 mt-4">
                        <button class="btn btn-secondary" onClick=${() => setShowSaveModal(false)}>Cancel</button>
                        <button class="btn btn-primary" onClick=${handleSaveRequest}>
                            ${editRequestId ? 'Update' : 'Save'}
                        </button>
                    </div>
                </div>
            </${Modal}>

            <!-- Import from Config Modal -->
            <${Modal} isOpen=${showImport} title="Import from Test Config" onClose=${() => { setShowImport(false); setImportOps([]); }} width="600px">
                <div>
                    ${importOps.length === 0 ? html`
                        <div class="form-group">
                            <label class="form-label">Select Test Config</label>
                            <div style="display: flex; flex-direction: column; gap: 8px;">
                                ${configs.map(c => html`
                                    <button key=${c.id} class="btn btn-ghost" style="text-align: left; justify-content: flex-start;"
                                        onClick=${() => handleImportFromConfig(c.id)}>
                                        <span style="font-weight: 500;">${c.name}</span>
                                        <span class="text-muted" style="margin-left: 8px; font-size: 12px;">${c.description || ''}</span>
                                    </button>
                                `)}
                                ${configs.length === 0 && html`<div class="text-muted">No test configs available</div>`}
                            </div>
                        </div>
                    ` : html`
                        <div>
                            <p class="text-muted" style="margin-bottom: 12px;">Config: <strong>${importConfigName}</strong></p>
                            <div style="display: flex; flex-direction: column; gap: 8px;">
                                ${importOps.map(op => html`
                                    <button key=${op.name} class="btn btn-ghost" style="text-align: left; justify-content: flex-start; padding: 12px;"
                                        onClick=${() => selectImportOp(op)}>
                                        <span class="badge" style="margin-right: 8px;">${op.type}</span>
                                        <span style="font-weight: 500;">${op.name}</span>
                                        ${!op.enabled && html`<span class="text-muted" style="margin-left: 8px;">(disabled)</span>`}
                                    </button>
                                `)}
                            </div>
                            <button class="btn btn-ghost btn-sm mt-3" onClick=${() => setImportOps([])}>← Back</button>
                        </div>
                    `}
                </div>
            </${Modal}>

            <${ConfirmDialog}
                isOpen=${!!deleteTarget}
                title="Delete Request"
                message=${`Delete "${deleteTarget?.name}"?`}
                onConfirm=${handleDeleteRequest}
                onCancel=${() => setDeleteTarget(null)}
                confirmLabel="Delete"
                danger=${true}
            />
        </div>
    `;
}
