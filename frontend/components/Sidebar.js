/**
 * Sidebar.js — Navigation sidebar with grouped links.
 */
import { h } from 'preact';
import htm from 'htm';
import { useAuth } from '../lib/auth.js';
import { navigate } from '../lib/router.js';

const html = htm.bind(h);

const NAV_SECTIONS = [
    {
        label: 'Overview',
        items: [
            { path: '/', label: 'Dashboard', icon: '⊞' },
        ],
    },
    {
        label: 'Performance Testing',
        items: [
            { path: '/test-configs', label: 'Test Configs', icon: '⚙' },
            { path: '/test-history', label: 'Test History', icon: '☰' },
            { path: '/compare', label: 'Compare', icon: '⇄' },
            { path: '/trends', label: 'Trends', icon: '↗' },
        ],
    },
    {
        label: 'Configuration',
        items: [
            { path: '/environments', label: 'Environments', icon: '◎' },
            { path: '/auth-providers', label: 'Auth Providers', icon: '🔑' },
        ],
    },
];

export function Sidebar({ currentPath }) {
    const { user, logout } = useAuth();

    const handleNav = (e, path) => {
        e.preventDefault();
        navigate(path);
    };

    const initial = user ? user.display_name?.charAt(0)?.toUpperCase() || user.username?.charAt(0)?.toUpperCase() || '?' : '?';

    return html`
        <aside class="sidebar">
            <div class="sidebar-logo">
                <div class="logo-icon">G</div>
                <h1>GraphQL Meter</h1>
            </div>

            ${NAV_SECTIONS.map(section => html`
                <div class="sidebar-section">
                    <div class="sidebar-section-label">${section.label}</div>
                    <nav class="sidebar-nav">
                        ${section.items.map(item => html`
                            <div class="sidebar-nav-item">
                                <a
                                    class="sidebar-nav-link ${currentPath === item.path ? 'active' : ''}"
                                    href="#${item.path}"
                                    onClick=${(e) => handleNav(e, item.path)}
                                >
                                    <span class="sidebar-nav-icon">${item.icon}</span>
                                    ${item.label}
                                </a>
                            </div>
                        `)}
                    </nav>
                </div>
            `)}

            ${user && html`
                <div class="sidebar-footer">
                    <div class="sidebar-user">
                        <div class="sidebar-user-avatar">${initial}</div>
                        <div class="sidebar-user-info">
                            <div class="sidebar-user-name">${user.display_name || user.username}</div>
                            <div class="sidebar-user-role">${user.role}</div>
                        </div>
                        <button class="btn btn-ghost btn-sm" onClick=${logout} title="Logout">⏻</button>
                    </div>
                </div>
            `}
        </aside>
    `;
}
