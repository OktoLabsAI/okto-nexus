import type {ReactNode} from 'react';
import {CheckCircle2, CircleHelp, Loader2, XCircle} from 'lucide-react';

/** A result indication driven by the canonical request state, never a timer. */
export function ConnectionOutcome({kind, title, children}: {
  kind: 'pending' | 'success' | 'failure' | 'unknown'; title: string; children?: ReactNode;
}) {
  const Icon=kind==='pending'?Loader2:kind==='success'?CheckCircle2:kind==='failure'?XCircle:CircleHelp;
  const color=kind==='success'?'border-green-500 text-green-700 dark:text-green-300':kind==='failure'?'border-red-500 text-red-700 dark:text-red-300':kind==='unknown'?'border-amber-500 text-amber-700 dark:text-amber-300':'border-accent-500';
  return <div role="status" aria-atomic="true" data-connection-outcome={kind} className={`rounded-xl border-2 p-4 ${color}`}>
    <div className="flex items-center gap-3"><Icon aria-hidden="true" className={`h-8 w-8 shrink-0 ${kind==='pending'?'animate-spin motion-reduce:animate-none':''}`} />
      <h3 className="text-xl font-semibold">{title}</h3></div>
    {children&&<div className="mt-2 text-sm text-surface-700 dark:text-surface-200">{children}</div>}
  </div>;
}

export const connectionSteps = ['Host & harness', 'Installation', 'Folders & login', 'Connection', 'Preferences', 'Authorization', 'Test'];

export type StepStatus = 'complete' | 'partial' | 'pending';
export function ConnectionWorkflow({step, summaries, onStep, available = step, locked = false, statuses, steps = connectionSteps}: {
  step: number; summaries: string[]; onStep: (step: number) => void; available?: number; locked?: boolean;
  statuses?: StepStatus[];
  steps?: string[];
}) {
  return <nav aria-label="Connection setup progress" className="rounded-xl bg-surface-50 dark:bg-surface-900 p-3">
    <ol className={steps.length === 1 ? 'grid grid-cols-1 gap-2' : steps.length === 3 ? 'grid grid-cols-3 gap-2' : 'grid grid-cols-2 md:grid-cols-4 xl:grid-cols-7 gap-2'}>
      {steps.map((title, index) => <li key={title}>
        <button type="button" aria-current={index === step ? 'step' : undefined}
          disabled={index > available || (locked && index !== step)} onClick={() => onStep(index)}
          className={`w-full h-full rounded-lg border p-3 text-left ${statuses?.[index] === 'pending' ? 'opacity-50' : ''} ${index === step ? 'border-accent-500 bg-accent-100 dark:bg-accent-900/40' : 'border-surface-200 dark:border-surface-700'}`}>
          <span className="block font-semibold">{index + 1}. {title}{statuses && <span
            aria-label={statuses[index] === 'complete' ? 'Complete' : statuses[index] === 'partial' ? 'Partial' : 'Not completed'}
            title={statuses[index] === 'complete' ? 'Complete' : statuses[index] === 'partial' ? 'Partial — review missing fields' : 'Not completed'}
            className={`ml-1 ${statuses[index] === 'complete' ? 'text-green-600' : statuses[index] === 'partial' ? 'text-amber-500' : 'text-surface-400'}`}>
            {statuses[index] === 'complete' ? '✓' : statuses[index] === 'partial' ? '◐' : '○'}</span>}</span>
          <span className="block text-xs mt-1 break-words text-surface-500 max-h-8 overflow-hidden" title={summaries[index]}>{summaries[index] || 'Not configured'}</span>
        </button>
      </li>)}
    </ol>
  </nav>;
}
