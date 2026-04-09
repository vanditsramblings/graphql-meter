/**
 * FeatureGate.js — Conditionally render children based on feature flag or role.
 */
import { h } from 'preact';
import htm from 'htm';
import { useAuth } from '../lib/auth.js';

const html = htm.bind(h);

export function FeatureGate({ flag, role, children, fallback }) {
    const { hasFlag, hasRole } = useAuth();

    let allowed = true;
    if (flag) allowed = hasFlag(flag);
    if (role) allowed = allowed && hasRole(role);

    if (allowed) return children;
    return fallback || null;
}
