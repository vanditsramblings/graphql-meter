/**
 * LineChart.js — Interactive SVG multi-series line chart with tooltips.
 */
import { h } from 'preact';
import { useState } from 'preact/hooks';
import htm from 'htm';

const html = htm.bind(h);

const COLORS = [
    'var(--chart-1)', 'var(--chart-2)', 'var(--chart-3)',
    'var(--chart-4)', 'var(--chart-5)', 'var(--chart-6)',
];

export function LineChart({ series = [], labels = [], width = 700, height = 300, yLabel = '' }) {
    const [tooltip, setTooltip] = useState(null);

    if (!series.length || !labels.length) {
        return html`
            <div class="card" style="height: ${height}px; display: flex; align-items: center; justify-content: center;">
                <span class="text-muted">No data available</span>
            </div>
        `;
    }

    const padding = { top: 20, right: 20, bottom: 40, left: 60 };
    const chartW = width - padding.left - padding.right;
    const chartH = height - padding.top - padding.bottom;

    const allValues = series.flatMap(s => s.data || []);
    const maxVal = Math.max(...allValues, 1);

    function getX(i) { return padding.left + (i / Math.max(labels.length - 1, 1)) * chartW; }
    function getY(v) { return padding.top + chartH - (v / maxVal) * chartH; }

    const yTicks = [0, 0.25, 0.5, 0.75, 1].map(pct => ({
        y: padding.top + chartH * (1 - pct),
        label: (maxVal * pct).toFixed(maxVal > 1000 ? 0 : maxVal > 10 ? 1 : 2),
    }));

    // X-axis labels (show ~6 labels max)
    const xStep = Math.max(1, Math.floor(labels.length / 6));
    const xTicks = labels.filter((_, i) => i % xStep === 0 || i === labels.length - 1).map((label, _, arr) => {
        const idx = labels.indexOf(label);
        return { x: getX(idx), label: label.length > 8 ? label.slice(0, 8) : label };
    });

    return html`
        <svg width="100%" viewBox="0 0 ${width} ${height}" style="display: block;"
            onMouseLeave=${() => setTooltip(null)}>

            <!-- Grid -->
            ${yTicks.map(t => html`
                <line x1=${padding.left} y1=${t.y} x2=${padding.left + chartW} y2=${t.y}
                    stroke="var(--border-weak)" stroke-width="1" stroke-dasharray="4,4" />
                <text x=${padding.left - 8} y=${t.y + 4} text-anchor="end"
                    fill="var(--text-secondary)" font-size="10" font-family="var(--font-mono)">
                    ${t.label}
                </text>
            `)}

            <!-- X labels -->
            ${xTicks.map(t => html`
                <text x=${t.x} y=${padding.top + chartH + 20} text-anchor="middle"
                    fill="var(--text-secondary)" font-size="10">
                    ${t.label}
                </text>
            `)}

            <!-- Y label -->
            ${yLabel && html`
                <text x="14" y=${padding.top + chartH / 2}
                    transform="rotate(-90, 14, ${padding.top + chartH / 2})"
                    text-anchor="middle" fill="var(--text-secondary)" font-size="11">
                    ${yLabel}
                </text>
            `}

            <!-- Series lines -->
            ${series.map((s, si) => {
                const data = s.data || [];
                if (data.length < 2) return null;
                const pathD = data.map((v, i) => `${i === 0 ? 'M' : 'L'}${getX(i).toFixed(1)},${getY(v).toFixed(1)}`).join(' ');
                return html`
                    <path d=${pathD} fill="none" stroke=${COLORS[si % COLORS.length]}
                        stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
                        opacity=${tooltip && tooltip.seriesIdx !== si ? 0.3 : 1} />
                `;
            })}

            <!-- Hover zones -->
            ${labels.map((_, i) => html`
                <rect
                    x=${getX(i) - chartW / labels.length / 2}
                    y=${padding.top}
                    width=${chartW / labels.length}
                    height=${chartH}
                    fill="transparent"
                    onMouseEnter=${() => {
                        const vals = series.map((s, si) => ({
                            name: s.name,
                            value: (s.data || [])[i],
                            color: COLORS[si % COLORS.length],
                        }));
                        setTooltip({ x: getX(i), label: labels[i], values: vals });
                    }}
                />
            `)}

            <!-- Tooltip -->
            ${tooltip && html`
                <line x1=${tooltip.x} y1=${padding.top} x2=${tooltip.x} y2=${padding.top + chartH}
                    stroke="var(--text-secondary)" stroke-width="1" stroke-dasharray="2,2" />
                <g>
                    <rect x=${Math.min(tooltip.x + 10, width - 150)} y=${padding.top + 10}
                        width="140" height=${30 + tooltip.values.length * 18}
                        rx="4" fill="var(--bg-secondary)" stroke="var(--border-medium)" />
                    <text x=${Math.min(tooltip.x + 18, width - 142)} y=${padding.top + 26}
                        fill="var(--text-primary)" font-size="11" font-weight="500">
                        ${tooltip.label}
                    </text>
                    ${tooltip.values.map((v, vi) => html`
                        <g>
                            <circle cx=${Math.min(tooltip.x + 22, width - 138)} cy=${padding.top + 42 + vi * 18}
                                r="4" fill=${v.color} />
                            <text x=${Math.min(tooltip.x + 32, width - 128)} y=${padding.top + 46 + vi * 18}
                                fill="var(--text-secondary)" font-size="10">
                                ${v.name}: ${v.value != null ? v.value.toFixed(1) : '—'}
                            </text>
                        </g>
                    `)}
                </g>
            `}

            <!-- Legend -->
            ${series.map((s, si) => html`
                <g>
                    <rect x=${padding.left + si * 100} y=${height - 14}
                        width="10" height="10" rx="2" fill=${COLORS[si % COLORS.length]} />
                    <text x=${padding.left + si * 100 + 14} y=${height - 5}
                        fill="var(--text-secondary)" font-size="10">
                        ${s.name}
                    </text>
                </g>
            `)}
        </svg>
    `;
}
