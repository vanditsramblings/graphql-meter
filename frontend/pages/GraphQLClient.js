/**
 * GraphQLClient.js — Built-in GraphQL client with nested folder collection tree.
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

const DEFAULT_QUERY = '# Write your GraphQL query here\nquery {\n  __typename\n}';

function headersToKV(hdrs) {
    try {
        const obj = typeof hdrs === 'string' ? JSON.parse(hdrs || '{}') : hdrs;
        const entries = Object.entries(obj);
        return entries.length > 0 ? entries.map(([k, v]) => ({ key: k, value: v })) : [{ key: '', value: '' }];
    } catch { return [{ key: '', value: '' }]; }
}
function kvToHeaders(kv) {
    const obj = {};
    (kv || []).forEach(({ key, value }) => { if (key.trim()) obj[key.trim()] = value; });
    return obj;
}
function kvToJSON(kv) { return JSON.stringify(kvToHeaders(kv), null, 2); }

/** Build a nested tree from flat folder paths and requests. */
function buildTree(requests, folderPaths) {
    const root = { children: {}, requests: [] };

    // Register all explicit folders
    for (const fp of folderPaths) {
        const parts = fp.split('/');
        let node = root;
        for (const p of parts) {
            if (!node.children[p]) node.children[p] = { children: {}, requests: [] };
            node = node.children[p];
        }
    }

    // Place requests
    for (const r of requests) {
        if (!r.folder_name) { root.requests.push(r); continue; }
        const parts = r.folder_name.split('/');
        let node = root;
        for (const p of parts) {
            if (!node.children[p]) node.children[p] = { children: {}, requests: [] };
            node = node.children[p];
        }
        node.requests.push(r);
    }
    return root;
}

function FolderNode({ name, path, node, depth, openFolders, toggleFolder, onSelectRequest, onDeleteRequest, onRenameFolder, onDeleteFolder, onNewSubFolder }) {
    const isOpen = openFolders[path];
    const childNames = Object.keys(node.children).sort();
    const totalCount = (function count(n) { let c = n.requests.length; for (const ch of Object.values(n.children)) c += count(ch); return c; })(node);

    return html`
        <div>
            <div style="padding: 3px 0 3px ${12 + depth * 16}px; display: flex; align-items: center; gap: 4px; cursor: pointer; font-size: var(--font-size-xs);"
                onClick=${() => toggleFolder(path)}
                class="tree-row">
                <${Icon} name=${isOpen ? 'chevron-down' : 'chevron-right'} size=${10} />
                <${Icon} name="folder" size=${12} style=${{ color: 'var(--status-warning)' }} />
                <span style="font-weight: 600; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${name}</span>
                <span class="text-muted" style="font-size: 10px; margin-right: 2px;">${totalCount}</span>
                <button class="btn btn-ghost tree-action" style="padding: 1px; min-width: 0; opacity: 0.4;"
                    onClick=${(e) => { e.stopPropagation(); onNewSubFolder(path); }} title="New sub-folder">
                    <${Icon} name="folder-plus" size=${10} />
                </button>
                <button class="btn btn-ghost tree-action" style="padding: 1px; min-width: 0; opacity: 0.4;"
                    onClick=${(e) => { e.stopPropagation(); onRenameFolder(path, name); }} title="Rename">
                    <${Icon} name="edit" size=${10} />
                </button>
                <button class="btn btn-ghost tree-action" style="padding: 1px; min-width: 0; opacity: 0.4;"
                    onClick=${(e) => { e.stopPropagation(); onDeleteFolder(path); }} title="Delete">
                    <${Icon} name="trash" size=${10} />
                </button>
            </div>
            ${isOpen && html`
                ${childNames.map(cn => html`
                    <${FolderNode}
                        key=${path + '/' + cn}
                        name=${cn}
                        path=${path + '/' + cn}
                        node=${node.children[cn]}
                        depth=${depth + 1}
                        openFolders=${openFolders}
                        toggleFolder=${toggleFolder}
                        onSelectRequest=${onSelectRequest}
                        onDeleteRequest=${onDeleteRequest}
                        onRenameFolder=${onRenameFolder}
                        onDeleteFolder=${onDeleteFolder}
                        onNewSubFolder=${onNewSubFolder}
                    />
                `)}
                ${node.requests.map(r => html`<${RequestItem} key=${r.id} r=${r} depth=${depth + 1} onSelect=${onSelectRequest} onDelete=${onDeleteRequest} />`)}
            `}
        </div>
    `;
}

function RequestItem({ r, depth, onSelect, onDelete }) {
    const isMutation = (r.query || '').trimStart().startsWith('mutation');
    return html`
        <div style="padding: 3px 0 3px ${12 + (depth || 0) * 16 + 16}px; cursor: pointer; display: flex; align-items: center; gap: 6px; font-size: var(--font-size-xs);"
            onClick=${() => onSelect(r.id)} class="tree-row">
            <span style=${{ color: isMutation ? 'var(--status-warning)' : 'var(--status-running)', fontWeight: 600, fontSize: '10px', minWidth: '14px' }}>${isMutation ? 'M' : 'Q'}</span>
            <span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1;" title=${r.name}>${r.name}</span>
            <button class="btn btn-ghost tree-action" style="padding: 2px; min-width: 0; opacity: 0.4;"
                onClick=${(e) => { e.stopPropagation(); onDelete(r); }}>
                <${Icon} name="trash" size=${10} />
            </button>
        </div>
    `;
}

export function GraphQLClient() {
    const { hasFlag } = useAuth();
    const toast = useToast();

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
    const [headerKV, setHeaderKV] = useState([{ key: '', value: '' }]);
    const [timeoutSec, setTimeoutSec] = useState(30);

    const [savedRequests, setSavedRequests] = useState([]);
    const [folderPaths, setFolderPaths] = useState([]);
    const [saveName, setSaveName] = useState('');
    const [saveFolderName, setSaveFolderName] = useState('');
    const [showSaveModal, setShowSaveModal] = useState(false);
    const [editRequestId, setEditRequestId] = useState(null);
    const [deleteTarget, setDeleteTarget] = useState(null);
    const [deleteFolderTarget, setDeleteFolderTarget] = useState(null);

    const [configs, setConfigs] = useState([]);
    const [showImport, setShowImport] = useState(false);
    const [importOps, setImportOps] = useState([]);
    const [importConfigName, setImportConfigName] = useState('');

    const [activePanel, setActivePanel] = useState('response');
    const [bottomPanel, setBottomPanel] = useState('variables');
    const [collectionOpen, setCollectionOpen] = useState(true);
    const [openFolders, setOpenFolders] = useState({});

    const [previewData, setPreviewData] = useState(null);
    const [showExport, setShowExport] = useState(false);
    const [exportContent, setExportContent] = useState('');
    const [exportFormat, setExportFormat] = useState('');

    const [showNewFolder, setShowNewFolder] = useState(false);
    const [newFolderParent, setNewFolderParent] = useState('');
    const [newFolderName, setNewFolderName] = useState('');
    const [renameFolderTarget, setRenameFolderTarget] = useState(null);
    const [renameFolderValue, setRenameFolderValue] = useState('');

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
            setFolderPaths((reqRes?.folders || []).map(f => f.path));
            setConfigs(cfgRes?.configs || []);
        } catch (e) {
            toast.error('Failed to load data');
        }
    };

    useEffect(() => { fetchData(); }, []);

    const getRequestBody = () => {
        let vars = {};
        try { vars = JSON.parse(variables || '{}'); } catch {}
        return {
            query, variables: vars, operation_name: operationName,
            environment_id: selectedEnvId, auth_provider_id: selectedAuthId,
            target_url: directUrl, headers: kvToHeaders(headerKV), timeout_sec: timeoutSec,
        };
    };

    const handleExecute = async () => {
        if (!query.trim()) { toast.warning('Query is required'); return; }
        try { JSON.parse(variables || '{}'); } catch { toast.warning('Variables must be valid JSON'); return; }
        setExecuting(true); setResponse(null);
        try {
            const res = await apiPost('/api/graphqlclient/execute', getRequestBody());
            setResponse(res); setActivePanel('response');
        } catch (e) {
            setResponse({ success: false, error: e.message || 'Execution failed' });
        } finally { setExecuting(false); }
    };

    const handleIntrospect = async () => {
        setExecuting(true); setResponse(null);
        try {
            const res = await apiPost('/api/graphqlclient/introspect', {
                environment_id: selectedEnvId, target_url: directUrl,
                auth_provider_id: selectedAuthId, headers: kvToHeaders(headerKV),
            });
            if (res?.success) toast.success('Found ' + res.query_count + ' queries and ' + res.mutation_count + ' mutations');
            else toast.error(res?.error || 'Introspection failed');
            setResponse(res); setActivePanel('response');
        } catch (e) { toast.error(e.message || 'Introspection failed'); }
        finally { setExecuting(false); }
    };

    const handlePreview = async () => {
        try { const res = await apiPost('/api/graphqlclient/preview', getRequestBody()); setPreviewData(res); setActivePanel('preview'); }
        catch (e) { toast.error(e.message || 'Preview failed'); }
    };

    const handleExport = async (format) => {
        try { const res = await apiPost('/api/graphqlclient/export/' + format, getRequestBody()); setExportContent(res?.content || ''); setExportFormat(format); setShowExport(true); }
        catch (e) { toast.error(e.message || 'Export failed'); }
    };

    const handleSaveRequest = async () => {
        if (!saveName.trim()) { toast.warning('Name is required'); return; }
        try {
            await apiPost('/api/graphqlclient/requests/save', {
                id: editRequestId, name: saveName, folder_name: saveFolderName,
                query, variables_json: variables, headers_json: kvToJSON(headerKV),
                environment_id: selectedEnvId, auth_provider_id: selectedAuthId, operation_name: operationName,
            });
            toast.success(editRequestId ? 'Request updated' : 'Request saved');
            setShowSaveModal(false); setSaveName(''); setSaveFolderName(''); setEditRequestId(null);
            fetchData();
        } catch (e) { toast.error(e.message || 'Save failed'); }
    };

    const loadSavedRequest = async (reqId) => {
        try {
            const res = await apiGet('/api/graphqlclient/requests/' + reqId);
            setQuery(res.query || '');
            setVariables(typeof res.variables_json === 'object' ? JSON.stringify(res.variables_json, null, 2) : (res.variables_json || '{}'));
            setHeaderKV(headersToKV(res.headers_json));
            setSelectedEnvId(res.environment_id || '');
            setSelectedAuthId(res.auth_provider_id || '');
            setOperationName(res.operation_name || '');
            setEditRequestId(res.id); setSaveName(res.name); setSaveFolderName(res.folder_name || '');
            toast.success('Loaded: ' + res.name);
        } catch (e) { toast.error('Failed to load request'); }
    };

    const handleImportFromConfig = async (configId) => {
        try {
            const res = await apiGet('/api/graphqlclient/from-config/' + configId);
            setImportOps(res?.operations || []); setImportConfigName(res?.config_name || '');
            if (res?.global_params?.host) setDirectUrl(res.global_params.host + (res.global_params.graphql_path || '/graphql'));
        } catch (e) { toast.error('Failed to load config operations'); }
    };

    const selectImportOp = (op) => {
        setQuery(op.query || (op.type + ' { ' + op.name + ' }'));
        setVariables(JSON.stringify(op.variables || {}, null, 2));
        setOperationName(op.name); setShowImport(false);
        toast.success('Imported: ' + op.name);
    };

    const handleDeleteRequest = async () => {
        if (!deleteTarget) return;
        try {
            await apiDelete('/api/graphqlclient/requests/' + deleteTarget.id);
            toast.success('Request deleted'); setDeleteTarget(null);
            if (editRequestId === deleteTarget.id) { setEditRequestId(null); setSaveName(''); }
            fetchData();
        } catch (e) { toast.error(e.message || 'Delete failed'); }
    };

    const handleDeleteFolder = async () => {
        if (!deleteFolderTarget) return;
        try {
            await apiPost('/api/graphqlclient/folders/delete', { folder_name: deleteFolderTarget });
            toast.success('Folder deleted'); setDeleteFolderTarget(null); fetchData();
        } catch (e) { toast.error(e.message || 'Delete failed'); }
    };

    const handleRenameFolder = async () => {
        if (!renameFolderTarget || !renameFolderValue.trim()) return;
        const oldPath = renameFolderTarget;
        const parts = oldPath.split('/');
        parts[parts.length - 1] = renameFolderValue.trim();
        const newPath = parts.join('/');
        try {
            await apiPost('/api/graphqlclient/folders/rename', { old_name: oldPath, new_name: newPath });
            toast.success('Folder renamed'); setRenameFolderTarget(null); setRenameFolderValue(''); fetchData();
        } catch (e) { toast.error(e.message || 'Rename failed'); }
    };

    const handleCreateFolder = async () => {
        if (!newFolderName.trim()) return;
        const fullPath = newFolderParent ? newFolderParent + '/' + newFolderName.trim() : newFolderName.trim();
        try {
            await apiPost('/api/graphqlclient/folders/create', { path: fullPath });
            toast.success('Folder created');
            setShowNewFolder(false); setNewFolderName(''); setNewFolderParent('');
            setOpenFolders(prev => ({ ...prev, [fullPath]: true }));
            fetchData();
        } catch (e) { toast.error(e.message || 'Create failed'); }
    };

    const updateHeaderKV = (idx, field, val) => setHeaderKV(prev => prev.map((h, i) => i === idx ? { ...h, [field]: val } : h));
    const addHeaderKV = () => setHeaderKV(prev => [...prev, { key: '', value: '' }]);
    const removeHeaderKV = (idx) => setHeaderKV(prev => prev.length <= 1 ? [{ key: '', value: '' }] : prev.filter((_, i) => i !== idx));
    const toggleFolder = (path) => setOpenFolders(prev => ({ ...prev, [path]: !prev[path] }));

    const selectedEnv = environments.find(e => e.id === selectedEnvId);

    // Build nested tree
    const tree = buildTree(savedRequests, folderPaths);
    const topFolderNames = Object.keys(tree.children).sort();

    // Collect all folder paths for the save dropdown
    const allFolderPaths = [];
    (function collect(node, prefix) {
        for (const [name, child] of Object.entries(node.children)) {
            const p = prefix ? prefix + '/' + name : name;
            allFolderPaths.push(p);
            collect(child, p);
        }
    })(tree, '');
    // Also include implicit folder paths from requests
    savedRequests.forEach(r => { if (r.folder_name && !allFolderPaths.includes(r.folder_name)) allFolderPaths.push(r.folder_name); });
    allFolderPaths.sort();

    return html`
        <div style="display: flex; flex-direction: column; height: calc(100vh - 80px);">
            <div class="page-header" style="flex-shrink: 0;">
                <div>
                    <h1 class="page-title">GraphQL Client</h1>
                    <p class="page-subtitle">Execute and verify GraphQL queries before load testing</p>
                </div>
                <div class="flex gap-2">
                    <button class="btn btn-ghost btn-sm" onClick=${() => setCollectionOpen(!collectionOpen)} title="Toggle collection">
                        <${Icon} name=${collectionOpen ? 'sidebar-close' : 'sidebar-open'} size=${14} style=${{ marginRight: '4px' }} /> Collection
                    </button>
                    <button class="btn btn-ghost btn-sm" onClick=${() => setShowImport(true)}><${Icon} name="download" size=${14} style=${{ marginRight: '4px' }} /> Import</button>
                    <button class="btn btn-ghost btn-sm" onClick=${() => { setShowSaveModal(true); if (!saveName) setSaveName(''); }}><${Icon} name="save" size=${14} style=${{ marginRight: '4px' }} /> Save</button>
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
                        <input class="form-input" value=${directUrl} onInput=${(e) => setDirectUrl(e.target.value)} placeholder="https://api.example.com/graphql" />
                    </div>
                `}
                <div style="min-width: 180px;">
                    <label class="form-label" style="font-size: 11px; margin-bottom: 2px;">Auth Provider</label>
                    <select class="form-select" value=${selectedAuthId} onChange=${(e) => setSelectedAuthId(e.target.value)}>
                        <option value="">— None —</option>
                        ${authProviders.map(p => html`<option key=${p.id} value=${p.id}>${p.name}</option>`)}
                    </select>
                </div>
                <button class="btn btn-primary" onClick=${handleExecute} disabled=${executing} style="height: 36px;">
                    ${executing ? 'Running...' : html`<${Icon} name="play" size=${14} style=${{ marginRight: '4px' }} /> Execute`}
                </button>
                <button class="btn btn-secondary btn-sm" onClick=${handleIntrospect} disabled=${executing} style="height: 36px;" title="Run introspection query">
                    <${Icon} name="search" size=${14} style=${{ marginRight: '4px' }} /> Introspect
                </button>
            </div>

            ${selectedEnv && html`
                <div style="flex-shrink: 0; padding: 6px 12px; background: var(--bg-tertiary); border-radius: var(--radius-md); margin-bottom: 8px; display: flex; gap: 16px; align-items: center; font-size: var(--font-size-xs);">
                    <span><strong>Host:</strong> ${selectedEnv.base_url}${selectedEnv.graphql_path || '/graphql'}</span>
                    <span><strong>Protocol:</strong> ${(selectedEnv.protocol || 'https').toUpperCase()}</span>
                    ${selectedEnv.tls_mode === 'mtls' && html`<span class="badge" style="font-size: 10px;">mTLS</span>`}
                    ${selectedEnv.auth_provider_id && html`<span><strong>Auth:</strong> <${Icon} name="key" size=${10} /> Linked</span>`}
                    ${!selectedEnv.verify_ssl && html`<span style="color: var(--status-warning);">SSL verification disabled</span>`}
                </div>
            `}

            <!-- Main Content -->
            <div style="flex: 1; display: flex; gap: 0; min-height: 0; overflow: hidden;">
                <!-- Collection Sidebar -->
                ${collectionOpen && html`
                    <div style="width: 260px; flex-shrink: 0; border-right: 1px solid var(--border-weak); display: flex; flex-direction: column; overflow: hidden;">
                        <div style="padding: 8px 12px; border-bottom: 1px solid var(--border-weak); display: flex; justify-content: space-between; align-items: center;">
                            <span style="font-weight: 600; font-size: var(--font-size-sm);"><${Icon} name="folder" size=${14} style=${{ marginRight: '4px' }} /> Collection</span>
                            <div class="flex gap-1">
                                <button class="btn btn-ghost" style="padding: 2px; min-width: 0;" title="New Folder"
                                    onClick=${() => { setShowNewFolder(true); setNewFolderParent(''); }}>
                                    <${Icon} name="folder-plus" size=${12} />
                                </button>
                                <span class="text-muted" style="font-size: var(--font-size-xs);">${savedRequests.length}</span>
                            </div>
                        </div>
                        ${showNewFolder && html`
                            <div style="padding: 6px 12px; border-bottom: 1px solid var(--border-weak);">
                                ${newFolderParent && html`<div style="font-size: 10px; color: var(--text-secondary); margin-bottom: 4px;">Inside: ${newFolderParent}</div>`}
                                <div style="display: flex; gap: 4px;">
                                    <input class="form-input" style="font-size: 11px; padding: 4px 6px; flex: 1;" value=${newFolderName}
                                        onInput=${(e) => setNewFolderName(e.target.value)} placeholder="Folder name"
                                        onKeyDown=${(e) => { if (e.key === 'Enter') handleCreateFolder(); if (e.key === 'Escape') { setShowNewFolder(false); setNewFolderName(''); } }} />
                                    <button class="btn btn-ghost" style="padding: 2px; min-width: 0;" onClick=${handleCreateFolder}><${Icon} name="check" size=${12} /></button>
                                    <button class="btn btn-ghost" style="padding: 2px; min-width: 0;" onClick=${() => { setShowNewFolder(false); setNewFolderName(''); }}><${Icon} name="x" size=${12} /></button>
                                </div>
                            </div>
                        `}
                        <div style="flex: 1; overflow-y: auto; padding: 4px 0;">
                            ${topFolderNames.map(fname => html`
                                <${FolderNode}
                                    key=${fname}
                                    name=${fname}
                                    path=${fname}
                                    node=${tree.children[fname]}
                                    depth=${0}
                                    openFolders=${openFolders}
                                    toggleFolder=${toggleFolder}
                                    onSelectRequest=${loadSavedRequest}
                                    onDeleteRequest=${(r) => setDeleteTarget(r)}
                                    onRenameFolder=${(path, name) => { setRenameFolderTarget(path); setRenameFolderValue(name); }}
                                    onDeleteFolder=${(path) => setDeleteFolderTarget(path)}
                                    onNewSubFolder=${(path) => { setNewFolderParent(path); setNewFolderName(''); setShowNewFolder(true); setOpenFolders(prev => ({ ...prev, [path]: true })); }}
                                />
                            `)}
                            ${tree.requests.length > 0 && html`
                                ${topFolderNames.length > 0 && html`
                                    <div style="padding: 4px 12px; font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-disabled); font-weight: 600; margin-top: 4px;">Unsorted</div>
                                `}
                                ${tree.requests.map(r => html`<${RequestItem} key=${r.id} r=${r} depth=${0} onSelect=${loadSavedRequest} onDelete=${(r) => setDeleteTarget(r)} />`)}
                            `}
                            ${savedRequests.length === 0 && topFolderNames.length === 0 && html`
                                <div class="text-muted" style="padding: 20px 12px; text-align: center; font-size: var(--font-size-xs);">
                                    No saved requests yet.
                                </div>
                            `}
                        </div>
                    </div>
                `}

                <!-- Editor + Response area -->
                <div style="flex: 1; display: flex; gap: 12px; min-height: 0; overflow: hidden; padding-left: ${collectionOpen ? '12px' : '0'};">
                <div style="flex: 1; display: flex; flex-direction: column; min-width: 0;">
                    <div style="flex: 1; display: flex; flex-direction: column;">
                        <label class="form-label" style="font-size: 11px; margin-bottom: 4px;">Query</label>
                        <textarea class="form-textarea text-mono"
                            style="flex: 1; resize: none; font-size: 13px; line-height: 1.5; background: var(--bg-primary); border-color: var(--border-weak);"
                            value=${query} onInput=${(e) => setQuery(e.target.value)} placeholder="Enter your GraphQL query..." />
                    </div>
                    <div style="margin-top: 8px;">
                        <div class="flex gap-2" style="margin-bottom: 4px;">
                            ${['variables', 'headers', 'settings'].map(p => html`
                                <button key=${p} class=${'btn btn-sm ' + (bottomPanel === p ? 'btn-primary' : 'btn-ghost')}
                                    onClick=${() => setBottomPanel(p)}>${p.charAt(0).toUpperCase() + p.slice(1)}</button>
                            `)}
                        </div>
                        ${bottomPanel === 'variables' && html`
                            <textarea class="form-textarea text-mono" rows="4" style="font-size: 12px; background: var(--bg-primary);"
                                value=${variables} onInput=${(e) => setVariables(e.target.value)} placeholder='{ "key": "value" }' />
                        `}
                        ${bottomPanel === 'headers' && html`
                            <div style="background: var(--bg-primary); border: 1px solid var(--border-weak); border-radius: var(--radius-md); padding: 8px; max-height: 140px; overflow-y: auto;">
                                ${headerKV.map((h, i) => html`
                                    <div key=${i} style="display: flex; gap: 4px; margin-bottom: 4px; align-items: center;">
                                        <input class="form-input" style="flex: 1; font-size: 11px; padding: 4px 6px; font-family: var(--font-mono);"
                                            value=${h.key} onInput=${(e) => updateHeaderKV(i, 'key', e.target.value)} placeholder="Header name" />
                                        <input class="form-input" style="flex: 2; font-size: 11px; padding: 4px 6px; font-family: var(--font-mono);"
                                            value=${h.value} onInput=${(e) => updateHeaderKV(i, 'value', e.target.value)} placeholder="Value" />
                                        <button class="btn btn-ghost" style="padding: 2px; min-width: 0;" onClick=${() => removeHeaderKV(i)}><${Icon} name="x" size=${10} /></button>
                                    </div>
                                `)}
                                <button class="btn btn-ghost btn-sm" style="font-size: 10px;" onClick=${addHeaderKV}>+ Add Header</button>
                            </div>
                        `}
                        ${bottomPanel === 'settings' && html`
                            <div class="card" style="padding: 12px;">
                                <div class="form-row">
                                    <div class="form-group" style="flex: 1;">
                                        <label class="form-label" style="font-size: 11px;">Operation Name</label>
                                        <input class="form-input" value=${operationName} onInput=${(e) => setOperationName(e.target.value)} placeholder="optional" />
                                    </div>
                                    <div class="form-group" style="width: 120px;">
                                        <label class="form-label" style="font-size: 11px;">Timeout (sec)</label>
                                        <input class="form-input" type="number" value=${timeoutSec} onInput=${(e) => setTimeoutSec(parseInt(e.target.value) || 30)} />
                                    </div>
                                </div>
                            </div>
                        `}
                    </div>
                </div>

                <div style="flex: 1; display: flex; flex-direction: column; min-width: 0;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                        <div class="flex gap-2">
                            ${['response', 'preview'].map(p => html`
                                <button key=${p} class=${'btn btn-sm ' + (activePanel === p ? 'btn-primary' : 'btn-ghost')}
                                    onClick=${() => { if (p === 'preview') handlePreview(); else setActivePanel(p); }}
                                    style="font-size: 11px;">${p.charAt(0).toUpperCase() + p.slice(1)}</button>
                            `)}
                            <button class="btn btn-ghost btn-sm" onClick=${() => handleExport('curl')} style="font-size: 11px;" title="Export as cURL">cURL</button>
                            <button class="btn btn-ghost btn-sm" onClick=${() => handleExport('postman')} style="font-size: 11px;" title="Export as Postman">Postman</button>
                        </div>
                        ${response && activePanel === 'response' && html`
                            <div class="flex gap-2" style="font-size: 11px;">
                                <span style="color: ${response.success ? 'var(--status-success)' : 'var(--status-error)'};">
                                    ${response.status_code ? 'HTTP ' + response.status_code : ''}
                                </span>
                                ${response.elapsed_ms != null && html`<span class="text-muted">${response.elapsed_ms}ms</span>`}
                            </div>
                        `}
                    </div>
                    <div style="flex: 1; overflow: auto; background: var(--bg-primary); border: 1px solid var(--border-weak); border-radius: var(--radius-md); padding: 12px;">
                        ${activePanel === 'response' && !response && !executing && html`
                            <div style="color: var(--text-disabled); text-align: center; padding-top: 40px;">Click Execute to run your query</div>
                        `}
                        ${activePanel === 'response' && executing && html`<${Spinner} size="sm" message="Executing..." />`}
                        ${activePanel === 'response' && response && html`
                            <pre class="text-mono" style="font-size: 12px; line-height: 1.5; color: var(--text-primary); white-space: pre-wrap; word-break: break-word; margin: 0;">${response.error ? response.error : JSON.stringify(response.response || response, null, 2)}</pre>
                        `}
                        ${activePanel === 'preview' && previewData && html`
                            <div style="font-size: 12px;">
                                <div style="margin-bottom: 12px;">
                                    <span class="badge" style="margin-right: 8px;">${previewData.method}</span>
                                    <span class="text-mono" style="color: var(--status-running);">${previewData.url}</span>
                                    ${previewData.has_cert && html`<span class="badge" style="margin-left: 8px; background: var(--accent-secondary)22; color: var(--accent-secondary);">mTLS</span>`}
                                </div>
                                <div style="margin-bottom: 12px;">
                                    <div class="form-label" style="font-size: 11px; margin-bottom: 4px;">Headers</div>
                                    <pre class="text-mono" style="font-size: 11px; margin: 0; padding: 8px; background: var(--bg-tertiary); border-radius: var(--radius-sm); white-space: pre-wrap;">${JSON.stringify(previewData.headers, null, 2)}</pre>
                                </div>
                                <div>
                                    <div class="form-label" style="font-size: 11px; margin-bottom: 4px;">Body</div>
                                    <pre class="text-mono" style="font-size: 11px; margin: 0; padding: 8px; background: var(--bg-tertiary); border-radius: var(--radius-sm); white-space: pre-wrap;">${JSON.stringify(previewData.body, null, 2)}</pre>
                                </div>
                            </div>
                        `}
                        ${activePanel === 'preview' && !previewData && html`
                            <div style="color: var(--text-disabled); text-align: center; padding-top: 40px;">Loading preview...</div>
                        `}
                    </div>
                    ${response?.response_headers && activePanel === 'response' && html`
                        <details style="margin-top: 8px;">
                            <summary class="text-muted" style="font-size: 11px; cursor: pointer;">Response Headers</summary>
                            <pre class="text-mono" style="font-size: 11px; color: var(--text-secondary); margin-top: 4px;">${JSON.stringify(response.response_headers, null, 2)}</pre>
                        </details>
                    `}
                </div>
            </div>
            </div>

            <!-- Save Request Modal -->
            <${Modal} isOpen=${showSaveModal} title=${editRequestId ? 'Update Request' : 'Save Request'} onClose=${() => setShowSaveModal(false)}>
                <div>
                    <div class="form-group">
                        <label class="form-label">Name *</label>
                        <input class="form-input" value=${saveName} onInput=${(e) => setSaveName(e.target.value)} placeholder="e.g., Get Users Query" />
                    </div>
                    <div class="form-group">
                        <label class="form-label">Folder</label>
                        <div class="flex gap-2">
                            <select class="form-select" style="flex: 1;" value=${saveFolderName} onChange=${(e) => setSaveFolderName(e.target.value)}>
                                <option value="">— No Folder —</option>
                                ${allFolderPaths.map(f => html`<option key=${f} value=${f}>${f}</option>`)}
                            </select>
                            <input class="form-input" style="flex: 1;" value=${saveFolderName}
                                onInput=${(e) => setSaveFolderName(e.target.value)} placeholder="or type new path (e.g. Auth/OAuth2)" />
                        </div>
                    </div>
                    <div class="flex justify-end gap-3 mt-4">
                        <button class="btn btn-secondary" onClick=${() => setShowSaveModal(false)}>Cancel</button>
                        <button class="btn btn-primary" onClick=${handleSaveRequest}>${editRequestId ? 'Update' : 'Save'}</button>
                    </div>
                </div>
            </${Modal}>

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
                            <button class="btn btn-ghost btn-sm mt-3" onClick=${() => setImportOps([])}>${'← Back'}</button>
                        </div>
                    `}
                </div>
            </${Modal}>

            <${Modal} isOpen=${showExport && !!exportContent} title=${'Export as ' + (exportFormat || '').toUpperCase()} onClose=${() => { setShowExport(false); setExportContent(''); }} width="650px">
                <div>
                    <pre class="text-mono" style="font-size: 11px; padding: 12px; background: var(--bg-tertiary); border-radius: var(--radius-md); white-space: pre-wrap; word-break: break-all; max-height: 400px; overflow-y: auto; margin: 0;">${exportContent}</pre>
                    <div class="flex justify-end gap-2 mt-3">
                        <button class="btn btn-primary btn-sm" onClick=${() => { navigator.clipboard.writeText(exportContent); toast.success('Copied to clipboard'); }}>
                            <${Icon} name="clipboard" size=${14} style=${{ marginRight: '4px' }} /> Copy
                        </button>
                        <button class="btn btn-secondary btn-sm" onClick=${() => {
                            const blob = new Blob([exportContent], { type: 'application/json' });
                            const url = URL.createObjectURL(blob);
                            const a = document.createElement('a');
                            a.href = url;
                            a.download = exportFormat === 'postman' ? 'collection.json' : 'request.sh';
                            a.click();
                            URL.revokeObjectURL(url);
                        }}>
                            <${Icon} name="download" size=${14} style=${{ marginRight: '4px' }} /> Download
                        </button>
                    </div>
                </div>
            </${Modal}>

            <${Modal} isOpen=${!!renameFolderTarget} title="Rename Folder" onClose=${() => setRenameFolderTarget(null)}>
                <div>
                    <div class="form-group">
                        <label class="form-label">New Name</label>
                        <input class="form-input" value=${renameFolderValue}
                            onInput=${(e) => setRenameFolderValue(e.target.value)}
                            onKeyDown=${(e) => { if (e.key === 'Enter') handleRenameFolder(); }} />
                    </div>
                    <div class="flex justify-end gap-3 mt-4">
                        <button class="btn btn-secondary" onClick=${() => setRenameFolderTarget(null)}>Cancel</button>
                        <button class="btn btn-primary" onClick=${handleRenameFolder}>Rename</button>
                    </div>
                </div>
            </${Modal}>

            <${ConfirmDialog}
                isOpen=${!!deleteTarget}
                title="Delete Request"
                message=${'Delete "' + (deleteTarget?.name || '') + '"?'}
                onConfirm=${handleDeleteRequest}
                onCancel=${() => setDeleteTarget(null)}
                confirmLabel="Delete"
                danger=${true}
            />

            <${ConfirmDialog}
                isOpen=${!!deleteFolderTarget}
                title="Delete Folder"
                message=${'Delete folder "' + (deleteFolderTarget || '') + '" and all sub-folders and requests?'}
                onConfirm=${handleDeleteFolder}
                onCancel=${() => setDeleteFolderTarget(null)}
                confirmLabel="Delete All"
                danger=${true}
            />
        </div>
    `;
}