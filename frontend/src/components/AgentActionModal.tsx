import { createContext, useContext, useEffect, useId, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { Maximize2, Minimize2, X } from 'lucide-react';
import './AgentActionModal.css';
import {CapturedModalChanges, type ModalChangeReceipt} from '../modalChanges';

const ModalContext = createContext<{footer: HTMLDivElement | null; dismiss: () => void; guard: (dirty: boolean, busy: boolean) => void;
  changes: ModalChangeReceipt; transition: (action: () => void) => void} | null>(null);

/** Use the same draft/busy guard when changing context inside the active panel. */
export function useAgentModalTransition() {
  const modal = useContext(ModalContext);
  return modal?.transition ?? ((action: () => void) => action());
}

/** Confirm captured edits only after canonical success or a confirmed new revision. */
export function useAgentModalChanges(): ModalChangeReceipt | null {
  return useContext(ModalContext)?.changes ?? null;
}

export function useAgentModalGuard(dirty: boolean, busy = false) {
  const modal = useContext(ModalContext);
  const guard = modal?.guard;
  useEffect(() => {guard?.(dirty, busy);}, [guard, dirty, busy]);
}
export function ModalCancelButton({children = 'Cancel', onClose}: {children?: ReactNode; onClose: () => void}) {
  const modal = useContext(ModalContext);
  return <button type="button" className="btn btn-secondary" onClick={modal?.dismiss || onClose}>{children}</button>;
}
export function AgentModalFooter({children}: {children: ReactNode}) {
  const modal = useContext(ModalContext);
  return modal ? (modal.footer && createPortal(children, modal.footer)) : <div className="flex items-center gap-2">{children}</div>;
}

export function AgentActionModal({title, children, onClose, wide = false, compact = false, guardChanges = true, testId, dirty = false, busy = false, presentation = 'modal'}: {
  title: string; children: ReactNode; onClose: () => void; wide?: boolean; compact?: boolean | 'tall'; guardChanges?: boolean; testId?: string; dirty?: boolean; busy?: boolean; presentation?: 'modal' | 'drawer' | 'terminal';
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const [expanded, setExpanded] = useState(false);
  const [discard, setDiscard] = useState(false);
  const [footer, setFooter] = useState<HTMLDivElement | null>(null);
  const pendingTransition = useRef<(() => void) | null>(null);
  const changed = useRef(new CapturedModalChanges());
  const changes = useRef<ModalChangeReceipt>({
    checkpoint: () => changed.current.checkpoint(),
    reset: checkpoint => {changed.current.reset(checkpoint);if (!changed.current.dirty) setDiscard(false);},
  }).current;
  const explicit = useRef({dirty: false, busy: false});
  const guard = useRef((dirty: boolean, busy: boolean) => {explicit.current = {dirty, busy};}).current;
  const close = useRef(onClose); close.current = onClose;
  const dismiss = () => {
    pendingTransition.current = null;
    if (busy || explicit.current.busy) return;
    if (guardChanges && (dirty || changed.current.dirty || explicit.current.dirty)) setDiscard(true);
    else close.current();
  };
  const transition = (action: () => void) => {
    if (busy || explicit.current.busy) return;
    if (guardChanges && (dirty || changed.current.dirty || explicit.current.dirty)) {
      pendingTransition.current = action;setDiscard(true);
    } else action();
  };
  const discardChanges = () => {
    const action = pendingTransition.current;pendingTransition.current = null;
    if (!action) {close.current();return;}
    changed.current.reset(changed.current.checkpoint());explicit.current = {dirty:false,busy:false};
    setDiscard(false);action();
  };
  useEffect(() => {
    const trigger = document.activeElement as HTMLElement | null;
    const element = dialog.current!;
    element.showModal();
    return () => {element.close(); if (trigger?.isConnected) trigger.focus({preventScroll:true});};
  }, []);
  return createPortal(<dialog ref={dialog} aria-labelledby={titleId} aria-modal="true" data-testid={testId}
    className={`agent-action-modal ${presentation === 'drawer' ? 'agent-action-drawer' : presentation === 'terminal' ? 'agent-action-terminal' : ''} ${wide ? 'agent-action-modal-wide' : ''} ${compact === 'tall' ? 'agent-action-modal-compact-tall' : compact ? 'agent-action-modal-compact' : ''} ${expanded ? 'agent-action-modal-expanded' : ''}`}
    onCancel={event => {event.preventDefault(); event.stopPropagation(); dismiss();}}>
    <ModalContext.Provider value={{footer, dismiss, guard, changes, transition}}>
      <header className="agent-modal-header">
        <h2 id={titleId}>{title}</h2>
        {presentation !== 'terminal' && <button type="button" aria-label={expanded ? 'Restore modal' : 'Expand modal'} title={expanded ? 'Restore' : 'Expand'} onClick={() => setExpanded(v => !v)}>
          {expanded ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
        </button>}
        <button type="button" aria-label={presentation === 'terminal' ? 'Back to Home' : 'Close modal'} title={presentation === 'terminal' ? 'Back to Home' : 'Close'} disabled={busy} onClick={dismiss}><X size={18} /></button>
      </header>
      {discard && <div className="agent-modal-discard" role="alert">
        <p>Discard unsaved changes?</p>
        <button className="btn btn-secondary" autoFocus onClick={() => {pendingTransition.current=null;setDiscard(false);}}>Keep editing</button>
        <button className="btn btn-danger" onClick={discardChanges}>Discard changes</button>
      </div>}
      <div className="agent-modal-body" onChangeCapture={event => {
        if (!(event.target instanceof Element) || !event.target.closest('[data-modal-passive]')) changed.current.capture();
      }}>{children}</div>
      <div className="agent-modal-footer" ref={setFooter} />
    </ModalContext.Provider>
  </dialog>, document.body);
}
