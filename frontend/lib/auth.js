/**
 * auth.js — Authentication context, login/logout, role checks.
 */
import { h, createContext } from 'preact';
import { useState, useContext, useCallback } from 'preact/hooks';
import htm from 'htm';
import { apiPost, apiCall } from './api.js';

const html = htm.bind(h);

const AuthContext = createContext(null);

const ROLE_HIERARCHY = { reader: 0, maintainer: 1, admin: 2 };

export function AuthProvider({ children }) {
    const [user, setUser] = useState(() => {
        try {
            const stored = localStorage.getItem('gqlm_user');
            return stored ? JSON.parse(stored) : null;
        } catch { return null; }
    });

    const [flags, setFlags] = useState(() => {
        try {
            const stored = localStorage.getItem('gqlm_flags');
            return stored ? JSON.parse(stored) : [];
        } catch { return []; }
    });

    const login = useCallback(async (username, password) => {
        const result = await apiPost('/api/auth/login', { username, password });
        if (result) {
            localStorage.setItem('gqlm_token', result.token);
            localStorage.setItem('gqlm_user', JSON.stringify(result.user));
            localStorage.setItem('gqlm_flags', JSON.stringify(result.flags));
            setUser(result.user);
            setFlags(result.flags);
            return result;
        }
        return null;
    }, []);

    const logout = useCallback(() => {
        localStorage.removeItem('gqlm_token');
        localStorage.removeItem('gqlm_user');
        localStorage.removeItem('gqlm_flags');
        setUser(null);
        setFlags([]);
        window.location.hash = '#/login';
    }, []);

    const hasRole = useCallback((minRole) => {
        if (!user) return false;
        return (ROLE_HIERARCHY[user.role] || -1) >= (ROLE_HIERARCHY[minRole] || 999);
    }, [user]);

    const hasFlag = useCallback((flag) => {
        return flags.includes(flag);
    }, [flags]);

    const value = { user, flags, login, logout, hasRole, hasFlag };

    return html`
        <${AuthContext.Provider} value=${value}>
            ${children}
        </${AuthContext.Provider}>
    `;
}

export function useAuth() {
    const ctx = useContext(AuthContext);
    if (!ctx) throw new Error('useAuth must be used within AuthProvider');
    return ctx;
}

export { AuthContext };
