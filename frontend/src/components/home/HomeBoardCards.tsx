import type {ReactNode} from 'react';
import type {HomeBoard,HomeBoardColumn,HomeBoardEntry,HomeBoardMetadata} from '../../homeTypes';

export const boardColumnLabels:Record<HomeBoardColumn,string>={active:'Active',needs_you:'Needs you',results:'Results'};
const columns:readonly HomeBoardColumn[]=['active','needs_you','results'];
type BoardView<T> = HomeBoardMetadata & {columns:Record<HomeBoardColumn,{items:T[];total:number|null;total_is_exact:boolean;has_more:boolean;next_cursor:string|null}>};
export function isQuietBoard(board:BoardView<unknown>|null,blocked=false):boolean{
  return !!board&&!blocked&&board.status==='ready'&&columns.every(name=>{
    const page=board.columns[name];return page.total_is_exact&&page.total===0&&!page.items.length;
  })&&Object.values(board.source_status).every(status=>status==='ready'||status==='disabled');
}

/** A single backend-partitioned relation; never classifies or merges source pages. */
export function HomeBoardCards<T extends {id:string}=HomeBoardEntry>({board,blocked,loading,initialLoading=true,onMore,renderEntry,onFocus,onBlur,countLabel='items',footer}: {
  board:BoardView<T>|null;blocked:boolean;loading:HomeBoardColumn|null;onMore:(column:HomeBoardColumn)=>void;
  renderEntry:(entry:T)=>ReactNode;onFocus:()=>void;onBlur:(inside:boolean)=>void;countLabel?:string|Record<HomeBoardColumn,string>;footer?:ReactNode;
  initialLoading?:boolean;
}) {
  return <section aria-labelledby="home-follow-up-title" data-testid="home-follow-up" className="space-y-3 min-w-0"
    onFocusCapture={onFocus} onBlurCapture={event=>onBlur(event.currentTarget.contains(event.relatedTarget as Node|null))}>
    <h2 id="home-follow-up-title" className="text-lg font-semibold">Follow-up</h2>
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 items-start" data-testid="home-board">
      {columns.map(column=>{
        const page=board?.columns[column],label=boardColumnLabels[column];
        const exactEmpty=board?.status==='ready'&&page?.total_is_exact&&page.total===0&&page.items.length===0;
        return <section key={column} aria-labelledby={'home-column-'+column} data-home-column={column} className="min-w-0 space-y-3 rounded-xl bg-surface-100/60 dark:bg-surface-900/50 p-3">
          <div className="flex flex-wrap justify-between items-baseline gap-2"><h3 id={'home-column-'+column} className="font-semibold">{label}</h3>
            <span className="text-xs text-surface-500">{page?.total===null||!page?'Total unknown':`${page.total_is_exact?'':'At least '}${page.total} ${typeof countLabel==='string'?countLabel:countLabel[column]}`}{blocked?' · Revalidating':''}</span></div>
          {!page&&<p role="status" className="text-sm text-surface-500">{initialLoading?`Loading ${label.toLowerCase()}…`:'This column is unavailable.'}</p>}
          {page&&<ul className="space-y-3">{page.items.map(entry=>renderEntry(entry))}</ul>}
          {page&&!page.items.length&&<p role="status" className="text-sm text-surface-500">{exactEmpty?`No ${label.toLowerCase()} items in this view.`:'Tracking is incomplete or unavailable. Refresh to read this column.'}</p>}
          {page?.has_more&&<button type="button" className="btn btn-secondary w-full" disabled={blocked||loading!==null} onClick={()=>onMore(column)}>
            {loading===column?'Loading…':`Load more ${label.toLowerCase()}`}</button>}
        </section>;
      })}
    </div>
    {footer}
  </section>;
}
