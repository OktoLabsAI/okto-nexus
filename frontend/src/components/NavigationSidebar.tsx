import {Bot, Files, House, Settings, Waypoints} from 'lucide-react';
import {PRIMARY_NAVIGATION, SECONDARY_NAVIGATION, getNavigationSectionId, type ViewId} from '../navigationRegistry';

const icons = {Home: House, 'Meta-harness': Bot, Graph: Waypoints, Artifacts: Files, Advanced: Settings};
export function NavigationSidebar({view, onNavigate, unread}: {
  view: ViewId; onNavigate: (id: ViewId) => void; unread: number;
}) {
  const selected = getNavigationSectionId(view);
  return <nav aria-label="Main navigation" className="flex-1 overflow-y-auto p-2 pt-3 space-y-4" data-testid="navigation-sidebar">
    {[PRIMARY_NAVIGATION, SECONDARY_NAVIGATION].map((entries, index) =>
      <ul key={index} className="space-y-1" aria-label={index === 0 ? 'Main destinations' : 'More destinations'}>
        {entries.map(entry => {
          const Icon = icons[entry.id as keyof typeof icons];
          return <li key={entry.id}><button type="button" data-view={entry.id}
            aria-current={selected === entry.id ? 'page' : undefined}
            onClick={() => onNavigate(entry.id)}
            className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-left text-sm transition-colors ${selected === entry.id
              ? 'bg-accent-100 text-accent-700 dark:bg-accent-900/60 dark:text-accent-200'
              : 'text-surface-700 hover:bg-surface-100 dark:text-surface-300 dark:hover:bg-surface-800'}`}>
            <Icon size={16} aria-hidden="true"/><span className="truncate">{entry.label}</span>
            {entry.id === 'Meta-harness' && Number.isSafeInteger(unread) && unread > 0 &&
              <span data-testid="unread-badge-Meta-harness" title="Unread messages addressed to the operator"
                className="ml-auto min-w-[18px] px-1.5 py-0.5 rounded-full bg-red-500 text-white text-[10px] font-semibold text-center leading-none">{unread}</span>}
          </button></li>;
        })}
      </ul>)}
  </nav>;
}
