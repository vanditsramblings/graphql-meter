/**
 * LiveChart.js — Real-time SVG chart for running tests.
 */
import { h } from 'preact';
import { useRef, useEffect } from 'preact/hooks';
import htm from 'htm';

const html = htm.bind(h);

export function LiveChart({ data = [], width = 600, height = 200, label = 'RPS', color = 'var(--chart-1)' }) {
    if (!data || data.length < 2) {
        return html`
            <div class="card" style="height: ${height}px; display: flex; align-items: center; justify-content: center;">
                <span class="text-muted">Waiting for data...</span>
            </div>
        `;
    }

    const maxVal = Math.max(...data.map(d => d.value || 0), 1);
    const padding = { top: 20, right: 10, bottom: 30, left: 50 };
    const chartW = width - padding.left - padding.right;
    const chartH = height - padding.top - padding.bottom;

    const points = data.map((d, i) => {
        const x = padding.left + (i / (data.length - 1)) * chartW;
        const y = padding.top + chartH - ((d.value || 0) / maxVal) * chartH;
        return { x, y, value: d.value, label: d.label };
    });

    const pathD = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ');
    const areaD = pathD + ` L${points[points.length - 1].x.toFixed(1)},${padding.top + chartH} L${points[0].x.toFixed(1)},${padding.top + chartH} Z`;

    // Y-axis labels
    const yTicks = [0, 0.25, 0.5, 0.75, 1].map(pct => ({
        y: padding.top + chartH * (1 - pct),
        label: (maxVal * pct).toFixed(maxVal > 100 ? 0 : 1),
    }));

    return html`
        <svg width="100%" viewBox="0 0 ${width} ${height}" style="display: block;">
            <defs>
                <linearGradient id="area-gradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stop-color=${color} stop-opacity="0.3" />
                    <stop offset="100%" stop-color=${color} stop-opacity="0.02" />
                </linearGradient>
            </defs>

            <!-- Grid lines -->
            ${yTicks.map(t => html`
                <line x1=${padding.left} y1=${t.y} x2=${padding.left + chartW} y2=${t.y}
                    stroke="var(--border-weak)" stroke-width="1" stroke-dasharray="4,4" />
                <text x=${padding.left - 8} y=${t.y + 4} text-anchor="end"
                    fill="var(--text-secondary)" font-size="10" font-family="var(--font-mono)">
                    ${t.label}
                </text>
            `)}

            <!-- Area -->
            <path d=${areaD} fill="url(#area-gradient)" />

            <!-- Line -->
            <path d=${pathD} fill="none" stroke=${color} stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />

            <!-- Current value -->
            ${points.length > 0 && html`
                <circle cx=${points[points.length - 1].x} cy=${points[points.length - 1].y} r="4" fill=${color} />
            `}

            <!-- Label -->
            <text x=${padding.left + 4} y=${padding.top - 6} fill="var(--text-secondary)" font-size="11" font-weight="500">
                ${label}: ${data[data.length - 1]?.value?.toFixed(1) || '0'}
            </text>
        </svg>
    `;
}
