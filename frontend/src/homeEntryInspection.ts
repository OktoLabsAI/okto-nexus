import type {HomeEntry, HomeEntryFilters, HomeEntryPage, HomeSessionRef, HomeTarget} from './homeTypes';
import type {AttentionAction,AttentionOccurrence} from './attentionTypes';

export interface HomeEntrySelection {
  groupId:string;entry:HomeEntry;filters:HomeEntryFilters;revision:string|null;
  attention?:{item:AttentionOccurrence;action:AttentionAction};
}
export function homeSessionRefKey(ref:HomeSessionRef):string {
  return JSON.stringify([ref.server_id,ref.executor_id,ref.workspace_id,ref.session_id]);
}
export function occurrenceSession(item:AttentionOccurrence,serverId:string):HomeSessionRef|null {
  if(item.source_type==='external_observation'||!item.session_id||!item.executor_id||!item.workspace_id)return null;
  return {server_id:serverId,executor_id:item.executor_id,workspace_id:item.workspace_id,session_id:item.session_id};
}
/** A unique proven relation or an explicit target; ordering never chooses a session. */
export function initialEntrySession(entry:HomeEntry,target:HomeTarget):HomeSessionRef|null {
  if(['session','execution','result'].includes(target.kind)&&'session_id' in target)
    return {server_id:target.server_id,executor_id:target.executor_id,workspace_id:target.workspace_id!,session_id:target.session_id};
  return entry.sessions_total===1&&entry.sessions.length===1?entry.sessions[0]:null;
}
export function assertEntryInspectionPage(page:HomeEntryPage<unknown>,selection:HomeEntrySelection,
  serverId:string,partition:'sessions'|'attention'|'results',revision:string|null):void {
  const f=selection.filters;
  if(page.version!==1||page.server_id!==serverId||page.partition!==partition||page.group_id!==selection.groupId||
    page.entry_id!==selection.entry.id||page.scope.workspace_id!==(f.workspace_id??null)||
    (page.scope.agent_id??'')!==(f.agent_id??'')||(page.scope.state??'')!==(f.state??'')||
    page.scope.quick!==(f.quick??'active')||page.scope.include_recent_results!==(f.quick===undefined)||
    (page.scope.harness??'')!==(f.harness??'')||(page.scope.host??'')!==(f.host??'')||
    revision!==null&&page.revision!==revision||!['ready','partial'].includes(page.status))
    throw new Error('This context changed. Close and reopen the row to review its current relations.');
}
