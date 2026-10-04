import { useId, type ReactNode } from 'react';

export function ConfigurationHelp({label, children}: {label: string; children: string}) {
  const id = useId();
  return <span className="relative inline-flex group ml-1 align-middle">
    <button type="button" aria-label={`Help: ${label}`} aria-describedby={id} title={children}
      className="rounded-full border w-4 h-4 text-[10px] leading-none text-surface-500 focus:outline focus:outline-2 focus:outline-accent-500">?</button>
    <span id={id} role="tooltip" className="hidden group-hover:block group-focus-within:block absolute left-0 top-6 z-50 w-64 rounded-lg border border-surface-300 bg-white p-3 text-xs font-normal text-surface-700 shadow-lg dark:bg-surface-900 dark:text-surface-200">{children}</span>
  </span>;
}

export function ConfigurationSection({title, status, children, initiallyOpen = false}: {
  title: string; status: string; children: ReactNode; initiallyOpen?: boolean;
}) {
  return <details open={initiallyOpen} className="rounded-xl border border-surface-200 dark:border-surface-700">
    <summary className="cursor-pointer px-4 py-3 font-semibold focus-visible:outline-accent-500">
      {title}<span className="ml-3 text-xs font-normal text-surface-500">{status}</span>
    </summary>
    <div className="px-4 pb-4 space-y-4">{children}</div>
  </details>;
}
