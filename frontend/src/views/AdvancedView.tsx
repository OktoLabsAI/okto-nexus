import {PageContainer} from '../components/PageContainer';
import {getAdvancedGroups, type ViewId} from '../navigationRegistry';

export function AdvancedView({memoryEnabled, onNavigate}: {
  memoryEnabled: boolean; onNavigate: (id: ViewId) => void;
}) {
  const groups = getAdvancedGroups({memoryEnabled});
  return <PageContainer testId="advanced-view" className="space-y-6">
    <header>
      <h1 className="text-xl font-semibold">Advanced</h1>
      <p className="mt-1 text-sm text-surface-500">Administration, history and diagnostics. Follow everyday work from Home.</p>
    </header>
    <div className="grid gap-6 md:grid-cols-2">
      {groups.map(group => <section key={group.id} aria-labelledby={`advanced-${group.id}`}>
        <h2 id={`advanced-${group.id}`} className="text-base font-semibold">{group.label}</h2>
        <p className="mt-1 text-sm text-surface-500">{group.description}</p>
        <ul className="mt-3 space-y-2">
          {group.entries.map(entry => <li key={entry.id}>
            <button type="button" className="w-full rounded-lg border border-surface-200 p-3 text-left hover:bg-surface-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary-500 dark:border-surface-700 dark:hover:bg-surface-800" onClick={() => onNavigate(entry.id)}>
              <span className="block text-sm font-medium">{entry.label}</span>
              <span className="mt-1 block text-sm text-surface-500">{entry.description}</span>
            </button>
          </li>)}
        </ul>
      </section>)}
    </div>
  </PageContainer>;
}
