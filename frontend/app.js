/**
 * app.js — Root application component.
 * AuthProvider → ToastProvider → Router → AuthGate → Layout → Routes
 */
import { h, render } from 'preact';
import htm from 'htm';
import { AuthProvider, useAuth } from './lib/auth.js';
import { useRoute, navigate } from './lib/router.js';
import { ToastProvider } from './components/Toast.js';
import { Layout } from './components/Layout.js';
import { Login } from './pages/Login.js';
import { Dashboard } from './pages/Dashboard.js';
import { TestConfigs } from './pages/TestConfigs.js';
import { TestHistory } from './pages/TestHistory.js';
import { TestRun } from './pages/TestRun.js';
import { Compare } from './pages/Compare.js';
import { Trends } from './pages/Trends.js';
import { Environments } from './pages/Environments.js';
import { AuthProviders } from './pages/AuthProviders.js';
import { GraphQLClient } from './pages/GraphQLClient.js';

const html = htm.bind(h);

function AppRouter() {
    const { user } = useAuth();
    const { path } = useRoute();

    // Redirect to login if not authenticated
    if (!user && path !== '/login') {
        navigate('/login');
        return null;
    }

    // Login page (no layout)
    if (path === '/login') {
        if (user) {
            navigate('/');
            return null;
        }
        return html`<${Login} />`;
    }

    // Route to page component
    let page;
    switch (path) {
        case '/':
            page = html`<${Dashboard} />`;
            break;
        case '/test-configs':
            page = html`<${TestConfigs} />`;
            break;
        case '/test-history':
            page = html`<${TestHistory} />`;
            break;
        case '/test-run':
            page = html`<${TestRun} />`;
            break;
        case '/compare':
            page = html`<${Compare} />`;
            break;
        case '/trends':
            page = html`<${Trends} />`;
            break;
        case '/environments':
            page = html`<${Environments} />`;
            break;
        case '/auth-providers':
            page = html`<${AuthProviders} />`;
            break;
        case '/graphql-client':
            page = html`<${GraphQLClient} />`;
            break;
        default:
            page = html`
                <div class="empty-state" style="padding: var(--space-10);">
                    <div class="empty-state-icon">404</div>
                    <div class="empty-state-title">Page Not Found</div>
                    <div class="empty-state-description">The page you're looking for doesn't exist.</div>
                    <button class="btn btn-primary" onClick=${() => navigate('/')}>Go to Dashboard</button>
                </div>
            `;
    }

    return html`
        <${Layout} currentPath=${path}>
            ${page}
        </${Layout}>
    `;
}

function App() {
    return html`
        <${AuthProvider}>
            <${ToastProvider}>
                <${AppRouter} />
            </${ToastProvider}>
        </${AuthProvider}>
    `;
}

// Mount
render(html`<${App} />`, document.getElementById('app'));
