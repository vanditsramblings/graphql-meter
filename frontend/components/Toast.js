/**
 * Toast.js — Toast notification system.
 */
import { h, createContext } from 'preact';
import { useState, useContext, useCallback, useEffect } from 'preact/hooks';
import htm from 'htm';

const html = htm.bind(h);

const ToastContext = createContext(null);

let toastId = 0;

export function ToastProvider({ children }) {
    const [toasts, setToasts] = useState([]);

    const addToast = useCallback((message, type = 'info', duration = 4000) => {
        const id = ++toastId;
        setToasts(prev => [...prev, { id, message, type }]);
        if (duration > 0) {
            setTimeout(() => {
                setToasts(prev => prev.filter(t => t.id !== id));
            }, duration);
        }
    }, []);

    const removeToast = useCallback((id) => {
        setToasts(prev => prev.filter(t => t.id !== id));
    }, []);

    const toast = {
        success: (msg) => addToast(msg, 'success'),
        error: (msg) => addToast(msg, 'error', 6000),
        warning: (msg) => addToast(msg, 'warning'),
        info: (msg) => addToast(msg, 'info'),
    };

    return html`
        <${ToastContext.Provider} value=${toast}>
            ${children}
            <div class="toast-container">
                ${toasts.map(t => html`
                    <div key=${t.id} class="toast toast-${t.type}">
                        <span>${t.message}</span>
                        <button class="toast-dismiss" onClick=${() => removeToast(t.id)}>×</button>
                    </div>
                `)}
            </div>
        </${ToastContext.Provider}>
    `;
}

export function useToast() {
    const ctx = useContext(ToastContext);
    if (!ctx) throw new Error('useToast must be used within ToastProvider');
    return ctx;
}
