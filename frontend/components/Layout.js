/**
 * Layout.js — Main app layout with sidebar and content area.
 */
import { h } from 'preact';
import htm from 'htm';
import { Sidebar } from './Sidebar.js';

const html = htm.bind(h);

export function Layout({ children, currentPath }) {
    return html`
        <div class="app-layout">
            <${Sidebar} currentPath=${currentPath} />
            <div class="main-content">
                <div class="content-area">
                    ${children}
                </div>
            </div>
        </div>
    `;
}
