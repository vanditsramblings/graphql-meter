/**
 * ErrorLog.js — Scrollable error display.
 */
import { h } from 'preact';
import { useRef, useEffect } from 'preact/hooks';
import htm from 'htm';

const html = htm.bind(h);

export function ErrorLog({ errors = [], maxHeight = '300px' }) {
    const bottomRef = useRef(null);

    useEffect(() => {
        if (bottomRef.current) {
            bottomRef.current.scrollIntoView({ behavior: 'smooth' });
        }
    }, [errors.length]);

    if (!errors.length) {
        return html`
            <div class="text-muted text-center" style="padding: var(--space-4);">
                No errors recorded
            </div>
        `;
    }

    return html`
        <div style="max-height: ${maxHeight}; overflow-y: auto; font-family: var(--font-mono); font-size: var(--font-size-xs);">
            ${errors.map((err, i) => {
                const ts = err.timestamp ? new Date(err.timestamp * 1000).toLocaleTimeString() : '';
                return html`
                    <div key=${i} style="
                        padding: var(--space-2) var(--space-3);
                        border-bottom: 1px solid var(--border-weak);
                        display: flex; gap: var(--space-3); align-items: flex-start;
                    ">
                        <span class="text-muted" style="white-space: nowrap; min-width: 70px;">${ts}</span>
                        <span class="badge-failed" style="padding: 1px 6px; font-size: 10px; white-space: nowrap;">
                            ${err.operation || err.status_code || 'ERR'}
                        </span>
                        <span style="color: var(--status-error); word-break: break-word;">
                            ${err.message || JSON.stringify(err)}
                        </span>
                    </div>
                `;
            })}
            <div ref=${bottomRef}></div>
        </div>
    `;
}
