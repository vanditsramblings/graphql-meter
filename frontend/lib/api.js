/**
 * api.js — API wrapper with JWT injection and auto-logout on 401.
 */

const BASE_URL = '';

export async function apiCall(path, opts = {}) {
    const token = localStorage.getItem('gqlm_token');
    const headers = {
        'Content-Type': 'application/json',
        ...(opts.headers || {}),
    };

    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }

    try {
        const response = await fetch(`${BASE_URL}${path}`, {
            ...opts,
            headers,
            body: opts.body ? (typeof opts.body === 'string' ? opts.body : JSON.stringify(opts.body)) : undefined,
        });

        if (response.status === 401) {
            localStorage.removeItem('gqlm_token');
            localStorage.removeItem('gqlm_user');
            localStorage.removeItem('gqlm_flags');
            window.location.hash = '#/login';
            return null;
        }

        if (!response.ok) {
            const err = await response.json().catch(() => ({ detail: response.statusText }));
            throw new Error(err.detail || `HTTP ${response.status}`);
        }

        return await response.json();
    } catch (error) {
        if (error.message !== 'Failed to fetch') {
            console.error(`API Error [${path}]:`, error.message);
        }
        throw error;
    }
}

export function apiGet(path) {
    return apiCall(path);
}

export function apiPost(path, body) {
    return apiCall(path, { method: 'POST', body });
}

export function apiPut(path, body) {
    return apiCall(path, { method: 'PUT', body });
}

export function apiDelete(path) {
    return apiCall(path, { method: 'DELETE' });
}
