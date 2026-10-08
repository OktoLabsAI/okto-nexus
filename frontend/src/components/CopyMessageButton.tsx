import { Check, Copy } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

export function CopyMessageButton({ text }: { text: string }) {
  const [status, setStatus] = useState<'idle' | 'copied' | 'error'>('idle');
  const timer = useRef<ReturnType<typeof setTimeout>>();
  useEffect(() => () => clearTimeout(timer.current), []);
  async function copy() {
    clearTimeout(timer.current);
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
      } else {
        // The dashboard also runs over HTTP on a trusted local network, where
        // the secure-context Clipboard API is not exposed by browsers.
        const focused = document.activeElement;
        const selection = window.getSelection();
        const ranges = selection ? Array.from({ length: selection.rangeCount }, (_, i) => selection.getRangeAt(i).cloneRange()) : [];
        const field = document.createElement('textarea');
        field.value = text;
        field.style.cssText = 'position:fixed;top:0;left:0;opacity:0;pointer-events:none';
        document.body.appendChild(field);
        try {
          field.focus({ preventScroll: true });
          field.select();
          if (!document.execCommand('copy')) throw new Error('Copy failed');
        } finally {
          field.remove();
          if (focused instanceof HTMLElement) focused.focus({ preventScroll: true });
          selection?.removeAllRanges();
          ranges.forEach(range => selection?.addRange(range));
        }
      }
      setStatus('copied');
      timer.current = setTimeout(() => setStatus('idle'), 2000);
    } catch {
      setStatus('error');
    }
  }
  const label = status === 'copied' ? 'Message copied' : status === 'error' ? 'Copy failed. Try again' : 'Copy message';
  return <>
    <button type="button" onClick={() => void copy()} aria-label={label} title={label}
      className="shrink-0 rounded p-1 text-surface-400 hover:bg-surface-100 hover:text-surface-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-500 dark:hover:bg-surface-800 dark:hover:text-surface-100">
      {status === 'copied' ? <Check size={14} /> : <Copy size={14} />}
    </button>
    <span className={status === 'error' ? 'text-xs text-red-500' : 'sr-only'} role="status">
      {status === 'copied' ? 'Message copied' : status === 'error' ? 'Could not copy. Select the message and copy it manually.' : ''}
    </span>
  </>;
}
