import type {HomeEntry, HomeEntryFilters, HomeEntryQuery,HomeEntryPage, HomeSessionRef, HomeTarget,HomeHarnessCard,HomeHarnessConnection,HomeSessionContext} from './homeTypes';
import type {AttentionAction,AttentionOccurrence} from './attentionTypes';
import {formatTime} from './timeFormat';

export interface HomeEntrySelection {
  groupId:string;entry:HomeEntry;filters:HomeEntryFilters;revision:string|null;
  presentationVersion?:1|2;
  attention?:{item:AttentionOccurrence;action:AttentionAction};
}
export interface HomeAttentionReturn {
  attentionId: string;
  action: AttentionAction;
  serverId: string;
  workspace: string | null;
  viewWorkspace: string;
  identityKey: string;
  target?: HomeTarget;
}
export function entryInspectionQuery(selection:HomeEntrySelection,cursor:string|null):HomeEntryQuery {
  return {...selection.filters,...(cursor?{cursor}:{}),limit:10,preview:3,
    ...(selection.presentationVersion===2?{presentation_version:2 as const}:{})};
}
export function homeSessionRefKey(ref:HomeSessionRef):string {
  return JSON.stringify([ref.server_id,ref.executor_id,ref.workspace_id,ref.session_id]);
}
export function homeSessionTarget(ref:HomeSessionRef):HomeTarget {
  return {kind:'session',server_id:ref.server_id,executor_id:ref.executor_id,workspace_id:ref.workspace_id,session_id:ref.session_id};
}

/** A work record can open the console only when it names an exact session. */
export function homeConsoleTarget(target:HomeTarget|null):Extract<HomeTarget,{kind:'session'}>|null {
  if(target?.kind==='session') return target;
  if(target?.kind!=='execution'||!target.workspace_id) return null;
  return {kind:'session',server_id:target.server_id,executor_id:target.executor_id,
    workspace_id:target.workspace_id,session_id:target.session_id};
}

export function homeWorkConsoleTarget(entry:HomeEntry,target:HomeTarget|null):HomeTarget|null {
  const exact=homeConsoleTarget(target);
  if(exact)return exact;
  if(target&&target.kind!=='handoff'&&target.kind!=='message')return null;
  if(entry.sessions_total!==1||entry.has_more_sessions!==false||entry.sessions_cursor!==null||entry.sessions?.length!==1)return null;
  const ref=entry.sessions[0];
  if(ref.lifecycle_state!=='READY'||ref.workspace_id!==entry.workspace_id||target&&target.server_id!==ref.server_id)return null;
  return homeSessionTarget(ref);
}
export function assertHarnessSessionContext(context:HomeSessionContext,connection:HomeHarnessConnection,ref:HomeSessionRef):void {
  if(context.session_id!==ref.session_id||(['server_id','executor_id','workspace_id'] as const).some(key=>ref[key]!==connection[key])||
    (['server_id','executor_id','workspace_id','binding_id','workspace_binding_id','agent_id'] as const)
    .some(key=>context[key]!==connection[key]))throw new Error('The session is not part of this exact connection.');
}
/** Only the complete binding relation proves uniqueness, never child previews. */
export function initialHarnessSession(card:HomeHarnessCard):HomeSessionRef|null {
  const {sessions,connection}=card;
  if(!Array.isArray(sessions)||!sessions.length||card.sessions_total!==sessions.length||card.has_more_sessions!==false||card.sessions_cursor!==null)return null;
  const seen=new Set<string>();
  let live:HomeSessionRef|null=null;
  for(const ref of sessions){
    if(ref.server_id!==connection.server_id||ref.executor_id!==connection.executor_id||ref.workspace_id!==connection.workspace_id||
      !ref.session_id||seen.has(ref.session_id))return null;
    seen.add(ref.session_id);
    if(ref.lifecycle_state==='CLOSED')continue;
    if(ref.lifecycle_state!=='READY'||live)return null;
    live=ref;
  }
  return sessions.length===1?sessions[0]:live;
}
export function homeSessionOptionLabel(ref:HomeSessionRef,index:number):string {
  const title=ref.title||`Session ${index+1}`;
  const parts=[title,ref.lifecycle_state||'State unknown',ref.workspace_label].filter(Boolean);
  if(ref.last_activity_at&&Number.isFinite(Date.parse(ref.last_activity_at)))parts.push(`Updated ${formatTime(ref.last_activity_at)}`);
  return parts.join(' · ');
}
export function occurrenceSession(item:AttentionOccurrence,serverId:string):HomeSessionRef|null {
  if(item.source_type==='external_observation'||!item.session_id||!item.executor_id||!item.workspace_id)return null;
  return {server_id:serverId,executor_id:item.executor_id,workspace_id:item.workspace_id,session_id:item.session_id};
}
/** A unique proven relation or an explicit target; ordering never chooses a session. */
export function initialEntrySession(entry:HomeEntry,target:HomeTarget):HomeSessionRef|null {
  if(['session','execution','result'].includes(target.kind)&&'session_id' in target)
    return {server_id:target.server_id,executor_id:target.executor_id,workspace_id:target.workspace_id!,session_id:target.session_id};
  return entry.sessions_total===1&&!entry.has_more_sessions&&entry.sessions.length===1?entry.sessions[0]:null;
}
export function assertEntryInspectionPage(page:HomeEntryPage<unknown>,selection:HomeEntrySelection,
  serverId:string,partition:'sessions'|'attention'|'results',revision:string|null):void {
  const f=selection.filters;
  const version=('presentation_version'in page?page.presentation_version:1)??1;
  if(page.version!==1||page.server_id!==serverId||page.partition!==partition||page.group_id!==selection.groupId||
    version!==(selection.presentationVersion??1)||
    page.entry_id!==selection.entry.id||page.scope.workspace_id!==(f.workspace_id??null)||
    (page.scope.agent_id??'')!==(f.agent_id??'')||(page.scope.state??'')!==(f.state??'')||
    page.scope.quick!==(f.quick??'active')||page.scope.include_recent_results!==(f.quick===undefined)||
    (page.scope.harness??'')!==(f.harness??'')||(page.scope.host??'')!==(f.host??'')||
    !['ready','partial'].includes(page.status)||!Array.isArray(page.items))
    throw new Error('This exact context is unavailable. No replacement was selected.');
  if(revision!==null&&page.revision!==revision)
    throw Object.assign(new Error('The relation changed.'),{status:409});
}

/** One bounded GET recovery. Scope/authority failures never trigger fallback. */
export async function readEntryInspectionPage<T>(read:(cursor:string|null)=>Promise<HomeEntryPage<T>>,
  cursor:string|null,selection:HomeEntrySelection,serverId:string,partition:'sessions'|'attention'|'results',
  revision:string|null,signal?:AbortSignal):Promise<{page:HomeEntryPage<T>;replaced:boolean}> {
  const current=()=>{if(signal?.aborted)throw new DOMException('Read cancelled.','AbortError');};
  try {
    const page=await read(cursor);current();assertEntryInspectionPage(page,selection,serverId,partition,revision);
    return {page,replaced:cursor===null};
  } catch(error) {
    current();
    if(!cursor||(error as {status?:number}).status!==409)throw error;
    const page=await read(null);current();assertEntryInspectionPage(page,selection,serverId,partition,null);
    return {page,replaced:true};
  }
}
