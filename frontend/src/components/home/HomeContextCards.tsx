import {FolderOpen, Layers, MessagesSquare, PackageCheck, Users} from 'lucide-react';
import type {WorkspaceListItem} from '../../api';
import type {HomeEntrySummary} from '../../homeTypes';
import {workspaceDisplayName} from '../WorkspaceNames';

/** One controlled project value; this component never reads or stores scope. */
export function HomeProjectCard({workspace,workspaces,onChange,onConnect,connectDisabled=false}: {
  workspace:string;workspaces:WorkspaceListItem[];onChange?:(id:string)=>void;
  onConnect:()=>void;connectDisabled?:boolean;
}) {
  const selected=workspaces.find(item=>item.workspace_id===workspace);
  const name=workspace==='all'?'All projects':selected?workspaceDisplayName(selected,workspaces.indexOf(selected)):'Unavailable project';
  return <section className="panel p-5 space-y-4" aria-label="Project" data-testid="home-project-card">
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div><h2 className="font-semibold text-base inline-flex items-center gap-2"><FolderOpen size={18}/>Project</h2>
        <p className="font-medium mt-2 break-words" data-testid="home-project-name">{name}</p>
        <p className="text-sm text-surface-500 mt-1">Choose a project, then connect or resume a collaborator.</p></div>
      <button type="button" className="btn btn-primary" disabled={connectDisabled} onClick={onConnect}>Connect or resume</button>
    </div>
    <label className="block text-sm space-y-1"><span>Choose a project</span>
      <select className="block w-full sm:max-w-md rounded-lg border border-surface-200 dark:border-surface-700 bg-transparent px-3 py-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-500"
        aria-label="Project" value={workspace} disabled={!onChange} onChange={event=>onChange?.(event.currentTarget.value)}>
        <option value="all">All projects</option>
        {workspace!=='all'&&!selected&&<option value={workspace}>Unavailable project</option>}
        {workspaces.map((item,index)=><option key={item.workspace_id} value={item.workspace_id}>{workspaceDisplayName(item,index)}</option>)}
      </select>
    </label>
  </section>;
}

/** These counters are supplied by one authorized backend Home snapshot. */
export function HomeSummaryCards({summary,stale=false}: {summary:HomeEntrySummary;stale?:boolean}) {
  const cards=[
    {key:'activities',title:'Work',detail:'Activities in this view',icon:Layers},
    {key:'sessions',title:'Sessions',detail:'Session contexts',icon:Users},
    {key:'occurrences',title:'Questions and updates',detail:'Items to review in this view',icon:MessagesSquare},
    {key:'results',title:'Results',detail:'Deliveries in this view',icon:PackageCheck},
  ] as const;
  return <section className="grid grid-cols-2 xl:grid-cols-4 gap-2 sm:gap-3" aria-label="Project overview" data-testid="home-summary-cards">
    {cards.map(({key,title,detail,icon:Icon})=>{
      const count=summary[key];
      return <div className="panel p-3 sm:p-5 min-w-0 break-words" key={key}><Icon size={19} className="text-accent-600 dark:text-accent-300 mb-2 sm:mb-3"/>
        <h2 className="font-semibold text-sm sm:text-base">{title}</h2>
        <p className="text-lg sm:text-2xl font-semibold mt-1 sm:mt-2">{count?.value===null||!count?'Not available':`${count.total_is_exact?'':'At least '}${count.value}`}</p>
        <p className="text-[11px] sm:text-xs text-surface-500 mt-1">{detail}{stale?' · Previous snapshot':''}</p>
      </div>;
    })}
  </section>;
}
