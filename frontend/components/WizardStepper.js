/**
 * WizardStepper.js — Step indicator for multi-step wizard.
 */
import { h } from 'preact';
import htm from 'htm';

const html = htm.bind(h);

export function WizardStepper({ steps, currentStep }) {
    return html`
        <div class="flex items-center gap-2" style="margin-bottom: var(--space-6);">
            ${steps.map((label, i) => {
                const stepNum = i + 1;
                const isActive = stepNum === currentStep;
                const isDone = stepNum < currentStep;
                const color = isDone ? 'var(--accent-primary)' : isActive ? 'var(--accent-primary)' : 'var(--text-disabled)';
                const bg = isDone ? 'var(--accent-dim)' : isActive ? 'var(--accent-primary)' : 'var(--bg-tertiary)';
                const textColor = isActive ? '#0b0c0e' : color;

                return html`
                    ${i > 0 && html`
                        <div style="flex: 1; height: 2px; background: ${isDone ? 'var(--accent-primary)' : 'var(--border-weak)'}; max-width: 60px;"></div>
                    `}
                    <div class="flex items-center gap-2" style="white-space: nowrap;">
                        <div style="
                            width: 28px; height: 28px; border-radius: 50%;
                            display: flex; align-items: center; justify-content: center;
                            font-size: var(--font-size-xs); font-weight: 600;
                            background: ${bg}; color: ${textColor};
                            border: 2px solid ${isDone || isActive ? 'var(--accent-primary)' : 'var(--border-medium)'};
                        ">${isDone ? '✓' : stepNum}</div>
                        <span style="font-size: var(--font-size-sm); color: ${isActive ? 'var(--text-primary)' : 'var(--text-secondary)'}; font-weight: ${isActive ? '500' : '400'};">
                            ${label}
                        </span>
                    </div>
                `;
            })}
        </div>
    `;
}
