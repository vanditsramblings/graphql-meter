/**
 * DataTable.js — Sortable, paginated table component.
 */
import { h } from 'preact';
import { useState, useMemo } from 'preact/hooks';
import htm from 'htm';

const html = htm.bind(h);

export function DataTable({ columns, data, pageSize = 20, onRowClick, emptyMessage = 'No data' }) {
    const [sortCol, setSortCol] = useState(null);
    const [sortDir, setSortDir] = useState('asc');
    const [page, setPage] = useState(0);

    const handleSort = (key) => {
        if (sortCol === key) {
            setSortDir(d => d === 'asc' ? 'desc' : 'asc');
        } else {
            setSortCol(key);
            setSortDir('asc');
        }
        setPage(0);
    };

    const sorted = useMemo(() => {
        if (!data || !sortCol) return data || [];
        return [...data].sort((a, b) => {
            const av = a[sortCol];
            const bv = b[sortCol];
            if (av == null && bv == null) return 0;
            if (av == null) return 1;
            if (bv == null) return -1;
            const cmp = typeof av === 'number' ? av - bv : String(av).localeCompare(String(bv));
            return sortDir === 'asc' ? cmp : -cmp;
        });
    }, [data, sortCol, sortDir]);

    const totalPages = Math.ceil((sorted?.length || 0) / pageSize);
    const paged = sorted.slice(page * pageSize, (page + 1) * pageSize);

    if (!data || data.length === 0) {
        return html`<div class="empty-state"><p>${emptyMessage}</p></div>`;
    }

    return html`
        <div>
            <div class="table-container">
                <table class="data-table">
                    <thead>
                        <tr>
                            ${columns.map(col => html`
                                <th
                                    key=${col.key}
                                    onClick=${() => col.sortable !== false && handleSort(col.key)}
                                    style=${col.width ? `width: ${col.width}` : ''}
                                >
                                    ${col.label}
                                    ${sortCol === col.key ? (sortDir === 'asc' ? ' ↑' : ' ↓') : ''}
                                </th>
                            `)}
                        </tr>
                    </thead>
                    <tbody>
                        ${paged.map((row, i) => html`
                            <tr
                                key=${row.id || i}
                                onClick=${() => onRowClick?.(row)}
                                style=${onRowClick ? 'cursor: pointer' : ''}
                            >
                                ${columns.map(col => html`
                                    <td key=${col.key}>
                                        ${col.render ? col.render(row[col.key], row) : row[col.key]}
                                    </td>
                                `)}
                            </tr>
                        `)}
                    </tbody>
                </table>
            </div>
            ${totalPages > 1 && html`
                <div class="flex items-center justify-between mt-4" style="padding: 0 4px;">
                    <span class="text-muted" style="font-size: var(--font-size-xs)">
                        Showing ${page * pageSize + 1}–${Math.min((page + 1) * pageSize, sorted.length)} of ${sorted.length}
                    </span>
                    <div class="flex gap-2">
                        <button class="btn btn-ghost btn-sm" onClick=${() => setPage(Math.max(0, page - 1))} disabled=${page === 0}>← Prev</button>
                        <button class="btn btn-ghost btn-sm" onClick=${() => setPage(Math.min(totalPages - 1, page + 1))} disabled=${page >= totalPages - 1}>Next →</button>
                    </div>
                </div>
            `}
        </div>
    `;
}
