/**
 * Spinner.js — Loading spinner component.
 */
import { h } from 'preact';
import htm from 'htm';

const html = htm.bind(h);

export function Spinner({ size = 'md', message }) {
    const cls = size === 'lg' ? 'spinner spinner-lg' : 'spinner';
    if (message) {
        return html`
            <div class="loading-state">
                <div class=${cls}></div>
                <span>${message}</span>
            </div>
        `;
    }
    return html`<div class=${cls}></div>`;
}
