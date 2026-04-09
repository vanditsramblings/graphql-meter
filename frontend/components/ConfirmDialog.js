/**
 * ConfirmDialog.js — Confirmation modal for destructive actions.
 */
import { h } from 'preact';
import htm from 'htm';
import { Modal } from './Modal.js';

const html = htm.bind(h);

export function ConfirmDialog({ isOpen, title, message, onConfirm, onCancel, confirmLabel = 'Confirm', danger = false }) {
    const footer = html`
        <button class="btn btn-secondary" onClick=${onCancel}>Cancel</button>
        <button class="btn ${danger ? 'btn-danger' : 'btn-primary'}" onClick=${onConfirm}>${confirmLabel}</button>
    `;

    return html`
        <${Modal} title=${title || 'Confirm'} isOpen=${isOpen} onClose=${onCancel} footer=${footer}>
            <p>${message || 'Are you sure?'}</p>
        </${Modal}>
    `;
}
