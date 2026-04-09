/**
 * StatusBadge.js — Colored badge for run status.
 */
import { h } from 'preact';
import htm from 'htm';

const html = htm.bind(h);

const STATUS_MAP = {
    running:   { cls: 'badge-running',   label: 'Running' },
    completed: { cls: 'badge-completed', label: 'Completed' },
    failed:    { cls: 'badge-failed',    label: 'Failed' },
    stopped:   { cls: 'badge-stopped',   label: 'Stopped' },
    pending:   { cls: 'badge-pending',   label: 'Pending' },
    success:   { cls: 'badge-success',   label: 'Success' },
    error:     { cls: 'badge-error',     label: 'Error' },
    warning:   { cls: 'badge-warning',   label: 'Warning' },
};

export function StatusBadge({ status, label }) {
    const info = STATUS_MAP[status] || STATUS_MAP.pending;
    return html`
        <span class="badge ${info.cls}">
            <span class="badge-dot"></span>
            ${label || info.label}
        </span>
    `;
}
