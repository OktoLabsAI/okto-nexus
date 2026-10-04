export const connectionSteps = ['Host & harness', 'Installation', 'Folders & login', 'Connection', 'Preferences', 'Authorization', 'Test'];

export function ConnectionWorkflow({step, summaries, onStep, available = step, locked = false}: {
  step: number; summaries: string[]; onStep: (step: number) => void; available?: number; locked?: boolean;
}) {
  return <nav aria-label="Connection setup progress" className="rounded-xl bg-surface-50 dark:bg-surface-900 p-3">
    <ol className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-7 gap-2">
      {connectionSteps.map((title, index) => <li key={title}>
        <button type="button" aria-current={index === step ? 'step' : undefined}
          disabled={index > available || (locked && index !== step)} onClick={() => onStep(index)}
          className={`w-full h-full rounded-lg border p-3 text-left disabled:opacity-50 ${index === step ? 'border-accent-500 bg-accent-100 dark:bg-accent-900/40' : 'border-surface-200 dark:border-surface-700'}`}>
          <span className="block font-semibold">{index + 1}. {title}</span>
          <span className="block text-xs mt-1 break-words text-surface-500 max-h-8 overflow-hidden" title={summaries[index]}>{summaries[index] || 'Not configured'}</span>
        </button>
      </li>)}
    </ol>
  </nav>;
}
