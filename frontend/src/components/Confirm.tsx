// Confirmation dialog (FR6/br_4099b53a): every destructive admin action
// must pass through here BEFORE any POST leaves the browser.
// Pulse modal grammar: blurred overlay, rounded-2xl content, slideUp.

import { type ReactNode, useState } from "react";
import { AgentActionModal, AgentModalFooter } from './AgentActionModal';

interface ConfirmState {
  title: string;
  body: ReactNode;
  onConfirm: () => void | Promise<void>;
}

export function useConfirm({agentModal = false}: {agentModal?: boolean} = {}) {
  const [state, setState] = useState<ConfirmState | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const dialog = state && agentModal ? <AgentActionModal title={state.title} onClose={() => setState(null)} guardChanges={false} busy={busy} compact testId="confirm-dialog">
    <div className="text-sm leading-relaxed">{state.body}</div>
    {error && <p role="alert" className="mt-3 text-xs text-red-600">{error}</p>}
    <AgentModalFooter>
      <button className="btn btn-secondary" disabled={busy} onClick={() => setState(null)}>Cancel</button>
      <button className="btn btn-danger" disabled={busy} onClick={async () => {
        setBusy(true); setError('');
        try {await state.onConfirm(); setState(null);}
        catch (failure) {setError(failure instanceof Error ? failure.message : String(failure));}
        finally {setBusy(false);}
      }}>{busy ? 'Working…' : 'Confirm'}</button>
    </AgentModalFooter>
  </AgentActionModal> : state ? (
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
          {error && <p role="alert" className="mt-3 text-red-600 dark:text-red-400">{error}</p>}
        </div>
        <div className="px-5 py-3 border-t border-surface-200/60 dark:border-surface-700/50 flex justify-end gap-2">
          <button className="btn btn-secondary" disabled={busy} onClick={() => setState(null)}>
            Cancel
          </button>
          <button
            className="btn btn-danger"
            disabled={busy}
            onClick={async () => {
              setBusy(true); setError("");
              try {
                await state.onConfirm();
                setState(null);
              } catch (failure) {
                setError(failure instanceof Error ? failure.message : String(failure));
              } finally { setBusy(false); }
            }}
          >
            {busy ? "Working…" : "Confirm"}
          </button>
        </div>
      </div>
    </div>
  ) : null;

  return { confirm: (next: ConfirmState | null) => {setError(""); setState(next);}, dialog };
}
