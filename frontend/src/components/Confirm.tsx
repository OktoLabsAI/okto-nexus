// Confirmation dialog (FR6/br_4099b53a): every destructive admin action
// must pass through here BEFORE any POST leaves the browser.
// Pulse modal grammar: blurred overlay, rounded-2xl content, slideUp.

import { type ReactNode, useState } from "react";

interface ConfirmState {
  title: string;
  body: ReactNode;
  onConfirm: () => void | Promise<void>;
}

export function useConfirm() {
  const [state, setState] = useState<ConfirmState | null>(null);

  const dialog = state ? (
    <div className="modal-overlay">
      <div
        className="modal-content w-[440px] max-w-[92vw]"
        role="dialog"
        aria-modal="true"
        data-testid="confirm-dialog"
      >
        <div className="px-5 py-4 border-b border-surface-200/60 dark:border-surface-700/50">
          <h3 className="font-display font-semibold text-sm text-surface-900 dark:text-surface-100">
            {state.title}
          </h3>
        </div>
        <div className="px-5 py-4 text-xs text-surface-600 dark:text-surface-400">
          {state.body}
        </div>
        <div className="px-5 py-3 border-t border-surface-200/60 dark:border-surface-700/50 flex justify-end gap-2">
          <button className="btn btn-secondary" onClick={() => setState(null)}>
            Cancel
          </button>
          <button
            className="btn btn-danger"
            onClick={async () => {
              await state.onConfirm();
              setState(null);
            }}
          >
            Confirm
          </button>
        </div>
      </div>
    </div>
  ) : null;

  return { confirm: setState, dialog };
}
