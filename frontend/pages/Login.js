/**
 * Login.js — Login page with username/password form.
 */
import { h } from 'preact';
import { useState } from 'preact/hooks';
import htm from 'htm';
import { useAuth } from '../lib/auth.js';
import { navigate } from '../lib/router.js';

const html = htm.bind(h);

export function Login() {
    const { login } = useAuth();
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError('');
        setLoading(true);
        try {
            const result = await login(username, password);
            if (result) {
                navigate('/');
            }
        } catch (err) {
            setError(err.message || 'Login failed');
        } finally {
            setLoading(false);
        }
    };

    return html`
        <div class="login-container">
            <div class="login-card">
                <div class="login-logo">
                    <img src="/favicon.svg" alt="GraphQL Meter" width="96" height="96" style="margin: 0 auto; display: block;" />
                    <h1>GraphQL Meter</h1>
                    <p>GraphQL Performance Testing Platform</p>
                </div>

                ${error && html`<div class="login-error">${error}</div>`}

                <form onSubmit=${handleSubmit}>
                    <div class="form-group">
                        <label class="form-label" for="username">Username</label>
                        <input
                            id="username"
                            class="form-input"
                            type="text"
                            value=${username}
                            onInput=${(e) => setUsername(e.target.value)}
                            placeholder="Enter username"
                            autocomplete="username"
                            required
                        />
                    </div>
                    <div class="form-group">
                        <label class="form-label" for="password">Password</label>
                        <input
                            id="password"
                            class="form-input"
                            type="password"
                            value=${password}
                            onInput=${(e) => setPassword(e.target.value)}
                            placeholder="Enter password"
                            autocomplete="current-password"
                            required
                        />
                    </div>
                    <button
                        class="btn btn-primary w-full btn-lg"
                        type="submit"
                        disabled=${loading || !username || !password}
                    >
                        ${loading ? 'Signing in...' : 'Sign In'}
                    </button>
                </form>

                <div style="margin-top: var(--space-5); text-align: center;">
                    <p class="text-muted" style="font-size: var(--font-size-xs);">
                        Demo accounts: admin / maintainer / reader
                    </p>
                </div>
            </div>
        </div>
    `;
}
