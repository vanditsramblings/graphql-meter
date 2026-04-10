/**
 * PercentageBar.js — Visual bar showing TPS% distribution.
 */
import { h } from 'preact';
import htm from 'htm';
import { Icon } from './Icons.js';

const html = htm.bind(h);

const COLORS = [
    'var(--chart-1)', 'var(--chart-2)', 'var(--chart-3)',
    'var(--chart-4)', 'var(--chart-5)', 'var(--chart-6)',
];

export function PercentageBar({ segments = [] }) {
    const total = segments.reduce((s, seg) => s + (seg.value || 0), 0);

    return html`
        <div>
            <div style="display: flex; height: 8px; border-radius: var(--radius-full); overflow: hidden; background: var(--bg-tertiary);">
                ${segments.map((seg, i) => html`
                    <div
                        key=${i}
                        style="width: ${seg.value || 0}%; background: ${COLORS[i % COLORS.length]}; transition: width 0.3s ease;"
                        title="${seg.label}: ${seg.value}%"
                    ></div>
                `)}
            </div>
            <div class="flex justify-between mt-2" style="font-size: var(--font-size-xs); color: var(--text-secondary);">
                <span>Total: ${total.toFixed(1)}%</span>
                <span class="${Math.abs(total - 100) < 0.1 ? 'text-success' : 'text-error'}">
                    ${Math.abs(total - 100) < 0.1 ? html`<${Icon} name="check-circle" size=${12} style=${{marginRight: '4px'}} /> Valid` : `${(100 - total).toFixed(1)}% remaining`}
                </span>
            </div>
        </div>
    `;
}
