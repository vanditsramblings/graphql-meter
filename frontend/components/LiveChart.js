/**
 * LiveChart.js — Multi-series interactive SVG chart.
 * Shows elapsed time on x-axis (Locust-style 0 → duration).
 * Each operation gets its own colored line. Interactive hover tooltip.
 */
import { h } from 'preact';
import { useState, useRef, useMemo, useCallback } from 'preact/hooks';
import htm from 'htm';

const html = htm.bind(h);

const COLORS = [
    '#6366f1', '#22d3ee', '#f59e0b', '#10b981', '#f43f5e',
    '#8b5cf6', '#06b6d4', '#ef4444', '#84cc16', '#ec4899',
];

function fmtElapsed(sec) {
    if (sec < 60) return sec.toFixed(0) + 's';
    const m = Math.floor(sec / 60);
    const s = Math.floor(sec % 60);
    return m + ':' + String(s).padStart(2, '0');
}

function fmtVal(v, unit) {
    if (v == null) return '—';
    if (unit === 'ms') return v >= 1000 ? (v / 1000).toFixed(2) + 's' : v.toFixed(1) + 'ms';
    return v.toFixed(1);
}

/**
 * @param {Object} props
 * @param {Array}  props.snapshots  - [{t, rps, op_rps: {name: val}, lat: {name: val}, ...}]
 * @param {string} props.field      - 'op_rps' for per-op RPS, 'lat' for per-op latency
 * @param {string} props.label      - Chart title
 * @param {string} props.unit       - 'rps' or 'ms'
 * @param {number} props.maxDuration - Fixed x-axis max (seconds)
 * @param {number} props.height     - SVG height
 * @param {string} props.chartId    - Unique ID for gradient defs
 */
export function LiveChart({ snapshots = [], field = 'op_rps', label = 'RPS', unit = 'rps', maxDuration = 0, height = 260, chartId = 'chart' }) {
    const containerRef = useRef(null);
    const [hoverIdx, setHoverIdx] = useState(null);

    // Extract unique operation names from all snapshots
    const opNames = useMemo(() => {
        const names = new Set();
        for (const s of snapshots) {
            const obj = s[field] || {};
            for (const k of Object.keys(obj)) names.add(k);
        }
        return [...names].sort();
    }, [snapshots, field]);

    if (!snapshots || snapshots.length < 2 || opNames.length === 0) {
        return html`
            <div style="height: ${height}px; display: flex; align-items: center; justify-content: center; border: 1px solid var(--border-weak); border-radius: var(--radius-md); background: var(--bg-secondary);">
                <span class="text-muted">Waiting for data...</span>
            </div>
        `;
    }

    const padding = { top: 28, right: 16, bottom: 32, left: 52 };
    const viewW = 900;
    const chartW = viewW - padding.left - padding.right;
    const chartH = height - padding.top - padding.bottom;

    const lastT = snapshots[snapshots.length - 1].t || 0;
    const xMax = maxDuration > 0 ? maxDuration : Math.max(lastT, 1);

    // Compute global max y across all series
    let maxVal = 1;
    for (const s of snapshots) {
        const obj = s[field] || {};
        for (const v of Object.values(obj)) {
            if (v > maxVal) maxVal = v;
        }
        if (field === 'op_rps' && s.rps > maxVal) maxVal = s.rps;
    }
    maxVal = maxVal * 1.1;

    const toX = (t) => padding.left + (t / xMax) * chartW;
    const toY = (v) => padding.top + chartH - (Math.max(0, v) / maxVal) * chartH;

    // Build series paths
    const series = opNames.map((name, i) => {
        const color = COLORS[i % COLORS.length];
        const points = snapshots.map(s => {
            const val = (s[field] || {})[name] || 0;
            return { x: toX(s.t), y: toY(val), value: val, t: s.t };
        });
        const pathD = points.map((p, j) => (j === 0 ? 'M' : 'L') + p.x.toFixed(1) + ',' + p.y.toFixed(1)).join(' ');
        return { name, color, points, pathD };
    });

    // Total line for RPS chart
    let totalSeries = null;
    if (field === 'op_rps') {
        const points = snapshots.map(s => ({ x: toX(s.t), y: toY(s.rps || 0), value: s.rps || 0, t: s.t }));
        const pathD = points.map((p, j) => (j === 0 ? 'M' : 'L') + p.x.toFixed(1) + ',' + p.y.toFixed(1)).join(' ');
        totalSeries = { name: 'Total', color: 'var(--text-muted)', points, pathD };
    }

    // Y-axis ticks
    const yTicks = [0, 0.25, 0.5, 0.75, 1].map(pct => ({
        y: padding.top + chartH * (1 - pct),
        label: fmtVal(maxVal * pct, unit),
    }));

    // X-axis ticks
    const xTickCount = 6;
    const xTicks = [];
    for (let t = 0; t < xTickCount; t++) {
        const elapsed = (t / (xTickCount - 1)) * xMax;
        xTicks.push({ x: toX(elapsed), label: fmtElapsed(elapsed) });
    }

    // Hover handler
    const handleMouseMove = useCallback((e) => {
        const container = containerRef.current;
        if (!container) return;
        const rect = container.getBoundingClientRect();
        const svgW = rect.width;
        const scaleX = viewW / svgW;
        const mouseX = (e.clientX - rect.left) * scaleX;
        const chartLeft = padding.left;
        const chartRight = viewW - padding.right;
        if (mouseX < chartLeft || mouseX > chartRight) { setHoverIdx(null); return; }
        const pct = (mouseX - chartLeft) / (chartRight - chartLeft);
        const targetT = pct * xMax;
        let bestIdx = 0;
        let bestDist = Infinity;
        for (let i = 0; i < snapshots.length; i++) {
            const dist = Math.abs(snapshots[i].t - targetT);
            if (dist < bestDist) { bestDist = dist; bestIdx = i; }
        }
        setHoverIdx(bestIdx);
    }, [snapshots, xMax]);

    const snap = hoverIdx != null ? snapshots[hoverIdx] : null;
    const hoverX = snap ? toX(snap.t) : 0;

    // Tooltip position: flip to left side if cursor is past 60% of chart
    const tooltipLeft = snap ? (hoverX / viewW) * 100 : 0;
    const flipTooltip = tooltipLeft > 60;

    return html`
        <div ref=${containerRef} style="position: relative;"
            onMouseMove=${handleMouseMove}
            onMouseLeave=${() => setHoverIdx(null)}>
            <svg width="100%" viewBox="0 0 ${viewW} ${height}" style="display: block; cursor: crosshair;">
                <!-- Grid lines -->
                ${yTicks.map(t => html`
                    <line x1=${padding.left} y1=${t.y} x2=${padding.left + chartW} y2=${t.y}
                        stroke="var(--border-weak)" stroke-width="0.5" />
                    <text x=${padding.left - 6} y=${t.y + 3} text-anchor="end"
                        fill="var(--text-secondary)" font-size="9" font-family="var(--font-mono)">
                        ${t.label}
                    </text>
                `)}

                <!-- X-axis labels -->
                ${xTicks.map(t => html`
                    <text x=${t.x} y=${padding.top + chartH + 18} text-anchor="middle"
                        fill="var(--text-secondary)" font-size="9" font-family="var(--font-mono)">
                        ${t.label}
                    </text>
                `)}

                <!-- Total line (dashed, if RPS chart) -->
                ${totalSeries && html`
                    <path d=${totalSeries.pathD} fill="none" stroke=${totalSeries.color}
                        stroke-width="1.5" stroke-dasharray="4,3" opacity="0.5" />
                `}

                <!-- Series lines -->
                ${series.map(s => html`
                    <path key=${s.name} d=${s.pathD} fill="none" stroke=${s.color}
                        stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
                `)}

                <!-- Hover crosshair + dots -->
                ${snap != null && html`
                    <line x1=${hoverX} y1=${padding.top} x2=${hoverX} y2=${padding.top + chartH}
                        stroke="var(--text-muted)" stroke-width="1" stroke-dasharray="3,3" opacity="0.6" />
                    ${series.map(s => html`
                        <circle key=${s.name} cx=${s.points[hoverIdx].x} cy=${s.points[hoverIdx].y}
                            r="3.5" fill=${s.color} stroke="var(--bg-primary)" stroke-width="1.5" />
                    `)}
                `}

                <!-- Label -->
                <text x=${padding.left + 4} y=${padding.top - 10} fill="var(--text-secondary)" font-size="11" font-weight="600">
                    ${label}
                </text>
            </svg>

            <!-- Legend -->
            <div style="display: flex; flex-wrap: wrap; gap: 10px 16px; padding: 4px 0 0 ${padding.left}px; font-size: 11px;">
                ${series.map(s => html`
                    <span key=${s.name} style="display: flex; align-items: center; gap: 4px;">
                        <span style="width: 10px; height: 3px; background: ${s.color}; border-radius: 1px;"></span>
                        <span style="color: var(--text-secondary);">${s.name}</span>
                    </span>
                `)}
                ${totalSeries && html`
                    <span style="display: flex; align-items: center; gap: 4px;">
                        <span style="width: 10px; height: 3px; background: var(--text-muted); border-radius: 1px; opacity: 0.5;"></span>
                        <span style="color: var(--text-muted);">Total</span>
                    </span>
                `}
            </div>

            <!-- Hover tooltip -->
            ${snap != null && html`
                <div class="chart-tooltip" style="left: ${tooltipLeft}%; top: ${padding.top}px; transform: translateX(${flipTooltip ? '-100%' : '0'});">
                    <div class="chart-tooltip-inner">
                        <div style="font-weight: 600; margin-bottom: 4px; color: var(--text-primary); border-bottom: 1px solid var(--border-weak); padding-bottom: 3px;">
                            ${fmtElapsed(snap.t)}
                        </div>
                        ${series.map(s => {
                            const val = (snap[field] || {})[s.name] || 0;
                            return html`
                                <div key=${s.name} style="display: flex; align-items: center; gap: 6px; padding: 1px 0;">
                                    <span style="width: 8px; height: 8px; border-radius: 50%; background: ${s.color}; flex-shrink: 0;"></span>
                                    <span style="flex: 1; color: var(--text-secondary); font-size: 11px;">${s.name}</span>
                                    <span style="font-weight: 500; font-family: var(--font-mono); font-size: 11px;">${fmtVal(val, unit)}</span>
                                </div>
                            `;
                        })}
                        ${totalSeries && html`
                            <div style="display: flex; align-items: center; gap: 6px; padding: 1px 0; border-top: 1px solid var(--border-weak); margin-top: 2px; padding-top: 3px;">
                                <span style="width: 8px; height: 8px; border-radius: 50%; background: var(--text-muted); flex-shrink: 0; opacity: 0.5;"></span>
                                <span style="flex: 1; color: var(--text-muted); font-size: 11px;">Total</span>
                                <span style="font-weight: 500; font-family: var(--font-mono); font-size: 11px;">${fmtVal(snap.rps, unit)}</span>
                            </div>
                        `}
                    </div>
                </div>
            `}
        </div>
    `;
}
