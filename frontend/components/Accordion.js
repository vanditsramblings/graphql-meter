/**
 * Accordion.js — Expandable/collapsible section.
 */
import { h } from 'preact';
import { useState } from 'preact/hooks';
import htm from 'htm';

const html = htm.bind(h);

export function Accordion({ title, defaultOpen = false, children, badge }) {
    const [open, setOpen] = useState(defaultOpen);

    return html`
        <div class="card" style="padding: 0; margin-bottom: var(--space-3);">
            <div
                class="flex items-center justify-between"
                style="padding: var(--space-3) var(--space-4); cursor: pointer; user-select: none;"
                onClick=${() => setOpen(!open)}
            >
                <div class="flex items-center gap-2">
                    <span style="font-size: var(--font-size-xs); opacity: 0.5;">${open ? '▼' : '▶'}</span>
                    <span style="font-weight: 500; font-size: var(--font-size-sm);">${title}</span>
                    ${badge != null && html`<span class="tab-count">${badge}</span>`}
                </div>
            </div>
            ${open && html`
                <div style="padding: 0 var(--space-4) var(--space-4); border-top: 1px solid var(--border-weak);">
                    ${children}
                </div>
            `}
        </div>
    `;
}
