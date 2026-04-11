/**
 * Modal.js — Overlay dialog component.
 */
import { h } from 'preact';
import { useEffect, useCallback } from 'preact/hooks';
import htm from 'htm';

const html = htm.bind(h);

export function Modal({ title, isOpen, onClose, children, footer, wide }) {
    const handleKeyDown = useCallback((e) => {
        if (e.key === 'Escape' && onClose) onClose();
    }, [onClose]);

    useEffect(() => {
        if (isOpen) {
            document.addEventListener('keydown', handleKeyDown);
            return () => document.removeEventListener('keydown', handleKeyDown);
        }
    }, [isOpen, handleKeyDown]);

    if (!isOpen) return null;

    const handleOverlayClick = (e) => {
        if (e.target === e.currentTarget) onClose?.();
    };

    return html`
        <div class="modal-overlay" onClick=${handleOverlayClick}>
            <div class="modal-content" style=${wide ? 'max-width: 900px' : ''}>
                <div class="modal-header">
                    <h3 class="modal-title">${title}</h3>
                    <button class="modal-close" onClick=${onClose}>×</button>
                </div>
                <div class="modal-body">
                    ${children}
                </div>
                ${footer && html`
                    <div class="modal-footer">
                        ${footer}
                    </div>
                `}
            </div>
        </div>
    `;
}
