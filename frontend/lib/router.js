/**
 * router.js — Hash-based router for SPA navigation.
 */
import { useState, useEffect, useCallback } from 'preact/hooks';

function getRoute() {
    const hash = window.location.hash.slice(1) || '/';
    const [path, query] = hash.split('?');
    const params = {};
    if (query) {
        for (const part of query.split('&')) {
            const [k, v] = part.split('=');
            params[decodeURIComponent(k)] = decodeURIComponent(v || '');
        }
    }
    return { path, params };
}

export function useRoute() {
    const [route, setRoute] = useState(getRoute);

    useEffect(() => {
        const handler = () => setRoute(getRoute());
        window.addEventListener('hashchange', handler);
        return () => window.removeEventListener('hashchange', handler);
    }, []);

    return route;
}

export function navigate(path, params = {}) {
    const query = Object.entries(params)
        .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
        .join('&');
    window.location.hash = query ? `#${path}?${query}` : `#${path}`;
}

export function matchRoute(pattern, path) {
    // Simple pattern matching: /test-run/:id
    const patternParts = pattern.split('/');
    const pathParts = path.split('/');

    if (patternParts.length !== pathParts.length) return null;

    const params = {};
    for (let i = 0; i < patternParts.length; i++) {
        if (patternParts[i].startsWith(':')) {
            params[patternParts[i].slice(1)] = pathParts[i];
        } else if (patternParts[i] !== pathParts[i]) {
            return null;
        }
    }
    return params;
}
