import type {RuntimeIntent,RuntimeOperation,RuntimeRequest,RuntimeResolution,RuntimeScope,RuntimeSession,runtimeApi} from '../../runtimeApi';
import type {AttentionTarget} from '../../attentionNavigation';
import {readAttentionReference} from '../../attentionNavigation';
import {assertContinuableSession,sameRuntimeScope} from './continuation';

export interface ExactRuntimeContext {
  scope:RuntimeScope;
  interruptTarget?: {kind:'native_turn_id';expected_turn_id:string};
}
const fields=['server_id','agent_id','executor_id','binding_id','workspace_id','workspace_binding_id','session_id'] as const;
export const exactRuntimeIntents:readonly RuntimeIntent[]=['turn.submit','turn.interrupt','runtime.close'];
export const exactRuntimeLabels:Partial<Record<RuntimeIntent,string>>={
  'turn.submit':'Continue this exact session',
  'turn.interrupt':'Interrupt the current run in this exact session',
  'runtime.close':'Close this exact session',
};
export function exactScopeKey(scope:RuntimeScope):string {
  if(fields.some(key=>typeof scope[key]!=='string'||!scope[key]))throw new Error('The exact runtime scope is incomplete.');
  return JSON.stringify(fields.map(key=>scope[key]));
}
export function exactStorageIdentity(scope:RuntimeScope,intent:RuntimeIntent):string[] {
  if(!exactRuntimeIntents.includes(intent))throw new Error('This intent cannot use exact-session recovery.');
  return ['home-exact',exactScopeKey(scope),intent];
}
export function assertExactRequest(request:RuntimeRequest,context:ExactRuntimeContext,allowed:readonly RuntimeIntent[]=exactRuntimeIntents):void {
  const scope=context.scope;
  exactScopeKey(scope);
  if(!exactRuntimeIntents.includes(request.intent)||!allowed.includes(request.intent)||request.new_session!==undefined||
      request.agent_id!==scope.agent_id||request.binding_id!==scope.binding_id||
      request.workspace_binding_id!==scope.workspace_binding_id||request.session_id!==scope.session_id)
    throw new Error('This action does not match the fixed session context. Recover the original request.');
  if(request.intent==='turn.interrupt') {
    const expected=context.interruptTarget||{kind:'current_run',expected_turn_id:null};
    if(request.target?.kind!==expected.kind||request.target.expected_turn_id!==expected.expected_turn_id)
      throw new Error('The interrupt does not match its explicit turn target.');
  }else if(request.target!==undefined)throw new Error('This intent does not accept an interrupt target.');
}
export function assertExactResolution(resolution:RuntimeResolution,request:RuntimeRequest,context:ExactRuntimeContext):void {
  const semantic=(resolution as RuntimeResolution&{semantic_intent?:{action?:string}}).semantic_intent;
  if(!sameRuntimeScope(resolution.scope,context.scope)||resolution.session_id!==context.scope.session_id||
      resolution.client_intent_id!==request.client_intent_id||semantic?.action!==request.intent)
    throw new Error('The resolved intent does not match this exact action and session.');
}
export async function revalidateExactContext(client:Pick<typeof runtimeApi,'session'|'binding'>,context:ExactRuntimeContext,intent:RuntimeIntent):Promise<void> {
  if(!exactRuntimeIntents.includes(intent))throw new Error('This context cannot open or select another session.');
  const scope=context.scope;
  const session=await client.session(scope.session_id,undefined,scope.executor_id);
  if(!sameRuntimeScope(session.scope,scope))throw new Error('The selected session changed scope. Reopen the exact context.');
  if(intent==='turn.submit')assertContinuableSession(session,scope);
  else if(!session.control_available||session.durable_release_pending||['CLOSED','FAILED','CLOSING','DRAINING'].includes(session.lifecycle_state)||session.lease_state==='CLOSED')
    throw new Error('Control is unavailable for this exact session. Inspect its current result.');
  const binding=await client.binding(scope.binding_id);
  if(binding.state!=='APPROVED'||binding.binding_id!==scope.binding_id||binding.agent_id!==scope.agent_id||
      binding.executor_id!==scope.executor_id||binding.workspace_id!==scope.workspace_id||
      binding.workspace_binding_id!==scope.workspace_binding_id)
    throw new Error('The selected binding changed scope or approval.');
}
export function mayDiscardExactRequest(record:{submissionAttempted:boolean;reviewAttempted?:boolean;reviewError?:string;resolution:unknown;quarantined?:boolean;recoveryConfirmed?:boolean},observed:boolean):boolean {
  if(record.quarantined)return record.submissionAttempted?observed:record.recoveryConfirmed===true;
  return record.submissionAttempted?observed:!!record.resolution||!!record.reviewError||record.reviewAttempted===false;
}
export function pendingExactRequests<T extends {request:RuntimeRequest;resolution:RuntimeResolution|null;submissionAttempted:boolean;
    reviewAttempted?:boolean;reviewError?:string;quarantined?:boolean}>(storage:Pick<Storage,'getItem'>,keyFor:(intent:RuntimeIntent)=>string,context:ExactRuntimeContext):T[] {
  const pending:T[]=[];
  for(const intent of exactRuntimeIntents) {
    const raw=storage.getItem(keyFor(intent));if(!raw)continue;
    const record=JSON.parse(raw) as T;
    if(!record.request||record.request.intent!==intent||typeof record.submissionAttempted!=='boolean'||typeof record.reviewAttempted!=='boolean')
      throw new Error('A retained exact action is invalid. Keep it for recovery; no new action was sent.');
    assertExactRequest(record.request,context);
    if(record.resolution)assertExactResolution(record.resolution,record.request,context);
    if(record.quarantined||record.submissionAttempted||record.reviewAttempted&&!record.resolution&&!record.reviewError)pending.push(record);
  }
  return pending;
}
// Never retain reviewed text, canonical free-form responses or output across logout.
// An attempted mutation still needs its original ID: absence is not proof of no effect.
export function quarantineExactRequest(record:{request:RuntimeRequest;resolution:RuntimeResolution|null;submissionAttempted:boolean;reviewAttempted?:boolean;recoveryRef?:Pick<RuntimeResolution,'operation_id'|'resolution_revision'|'intent_hash'|'expires_at'>}):unknown {
  const request=record.request;
  const resolution=record.resolution||record.recoveryRef;
  return {request:{client_intent_id:request.client_intent_id,intent:request.intent,agent_id:request.agent_id,
    binding_id:request.binding_id,workspace_binding_id:request.workspace_binding_id,session_id:request.session_id,
    ...(request.target?{target:{kind:request.target.kind,expected_turn_id:request.target.expected_turn_id}}: {})},resolution:null,submissionAttempted:record.submissionAttempted,
    reviewAttempted:record.reviewAttempted!==false,quarantined:true,
    ...(resolution?{recoveryRef:{operation_id:resolution.operation_id,resolution_revision:resolution.resolution_revision,
      intent_hash:resolution.intent_hash,expires_at:resolution.expires_at}}:{})};
}
export function clearExactRuntimeRequests(storage:Pick<Storage,'length'|'key'|'getItem'|'setItem'|'removeItem'>):void {
  const keys:string[]=[];
  for(let i=0;i<storage.length;i++) {
    const key=storage.key(i);if(!key?.startsWith('okto-nexus:r4-runtime:'))continue;
    try {const value=JSON.parse(key.slice('okto-nexus:r4-runtime:'.length));
      if(Array.isArray(value)&&value.length===8&&value[4]==='home-exact'&&typeof value[5]==='string'&&exactRuntimeIntents.includes(value[6]))keys.push(key);}
    catch { /* Unrelated/malformed local records stay available for diagnosis. */ }
  }
  for(const key of keys){
    try {const record=JSON.parse(storage.getItem(key)||'null');
      if(record?.quarantined&&record.invalid)continue;
      if(record?.request&&(record.submissionAttempted||record.reviewAttempted!==false&&!record.reviewError))
        storage.setItem(key,JSON.stringify(quarantineExactRequest(record)));
      else storage.removeItem(key);
    }catch { // Do not preserve protected malformed content; keep a blocking tombstone.
      storage.setItem(key,JSON.stringify({quarantined:true,invalid:true}));
    }
  }
}
export async function readExactExecutionContext(canonical:Parameters<typeof readAttentionReference>[0],
    runtime:Pick<typeof runtimeApi,'me'|'session'|'binding'>,target:Extract<AttentionTarget,{kind:'execution'}>,signal?:AbortSignal) {
  const active=()=>{if(signal?.aborted)throw new DOMException('Read cancelled.','AbortError');};
  active();
  const selected=await readAttentionReference(canonical,target,signal);
  active();
  if(selected.kind!=='execution')throw new Error('An exact execution reference is required.');
  const operation:RuntimeOperation=selected.record;
  exactScopeKey(operation.scope);
  const context=await readExactSessionContext(runtime,operation.scope,signal);
  return {operation,...context};
}
export async function readExactSessionContext(runtime:Pick<typeof runtimeApi,'me'|'session'|'binding'>,scope:RuntimeScope,signal?:AbortSignal) {
  const active=()=>{if(signal?.aborted)throw new DOMException('Read cancelled.','AbortError');};
  exactScopeKey(scope);active();
  const me=await runtime.me(signal);
  active();
  if(me.server_id!==scope.server_id)throw new Error('The execution belongs to another Server.');
  const session:RuntimeSession=await runtime.session(scope.session_id,signal,scope.executor_id);
  active();
  if(!sameRuntimeScope(scope,session.scope))throw new Error('The execution session no longer matches its full scope.');
  const binding=await runtime.binding(scope.binding_id);
  active();
  if(binding.binding_id!==scope.binding_id||binding.agent_id!==scope.agent_id||binding.executor_id!==scope.executor_id||
      binding.workspace_id!==scope.workspace_id||binding.workspace_binding_id!==scope.workspace_binding_id)
    throw new Error('The execution binding no longer matches its full scope.');
  return {session,binding};
}
