import { codexAdapter } from './codex';
import { claudeAdapter } from './claude';
import { piAdapter } from './pi';
import { clean, content, fields, label, object, string, withoutNativeText, type ActionUpdate, type AdapterContext, type SessionEvent, type TerminalAction } from './model';
export type { TerminalAction } from './model';
export const harnessAdapters = [codexAdapter,claudeAdapter,piAdapter];
const metadata = new Set(['type','thread_id','threadId','turn_id','turnId','session_id','sessionId','delivery_phase','delivery_outcome','native_approval','native_approval_display','raw','usage','modelUsage','output_text','final','index','id']);

export function fallback(event: SessionEvent): ActionUpdate[] {
  const p=object(event.payload), type=event.native_type || event.category;
  const id=`event:${event.stream_epoch}:${event.sequence}`;
  if (!Object.keys(p).length) return event.category==='error' ? [{id,kind:'error',title:label(type)}] : [];
  if (event.category==='approval_request' || event.category==='input_request') {
    const safe=object(p.native_approval_display), request=object(p.request || safe.params);
    return [{id,kind:'approval',title:event.category==='input_request'?'Input requested':'Approval requested',fields:fields(request),text:string(p.message)}];
  }
  if (event.category==='error' || p.is_error || p.delivery_outcome==='failed') return [{id,kind:'error',title:'Execution failed',
    text:content(p.error || p.errors || p.message || p.stderr_tail || p.delivery_error_code) || label(type)}];
  if (p.delivery_phase==='started') return [{id,kind:'status',title:'Turn started'}];
  if (p.delivery_phase==='terminal') return [{id,kind:'status',title:p.delivery_outcome==='interrupted'?'Turn interrupted':'Turn completed'}];
  if (event.category==='text_delta' || event.category==='text_snapshot') return [{id,kind:'assistant',title:'Assistant',text:string(p.output_text || p.text)}];
  if (type==='core/harness_configuration') return [{id,kind:'status',title:'Harness ready',text:string(object(p.harness_configuration).adapter_id)}];
  const meaningful=Object.fromEntries(Object.entries(p).filter(([k])=>!metadata.has(k)));
  const details=fields(meaningful);
  return details.length ? [{id,kind:'status',title:label(type),fields:details}] : [];
}

// Both paged history and tail consume the same presentation pipeline. Adapters
// interpret native vocabulary; only this reducer and the renderer own layout.
export function presentEvents(events: SessionEvent[], harness?: string): TerminalAction[] {
  const context: AdapterContext={turn:'initial',message:'initial',serial:0,blocks:new Map(),partialInputs:new Map(),messageFinished:false};
  const actions: TerminalAction[]=[], positions=new Map<string,number>();
  // Core's public output is the only canonical text stream. Native snapshots
  // can repeat that text; native deltas deliberately contain only placeholders.
  // Match the server projection: snapshots replace, deltas and terminal flushes
  // append. Never fall back to raw text when output_text is an empty holdback.
  const groups=new Map<SessionEvent,string>(), normalized=new Set<string>();
  let group='';
  for (const event of events) {
    const p=object(event.payload);
    if (!group.startsWith(`${event.stream_epoch}:`) || p.delivery_phase==='started') group=`${event.stream_epoch}:${event.sequence}`;
    groups.set(event,group);
    if (typeof p.output_text==='string' && ['text_delta','text_snapshot'].includes(event.category)) normalized.add(group);
  }
  let adapter=harnessAdapters.find(a=>a.id===harness), epoch='';
  for (const original of events) {
    const event={...original,payload:withoutNativeText(original.payload)};
    if (epoch!==event.stream_epoch) {positions.clear();epoch=event.stream_epoch;context.turn=`epoch:${epoch}`;}
    const p=object(event.payload);
    if (p.delivery_phase==='started') {
      context.turn=string(p.turn_id || p.turnId || object(p.turn).id) || String(event.sequence);
      context.message='initial';context.blocks.clear();context.partialInputs.clear();context.messageFinished=false;
    }
    adapter ||= harnessAdapters.find(a=>a.matches(event));
    let updates=event.category==='approval_request' || event.category==='input_request' || event.category==='error'
      ? fallback(event) : adapter?.adapt(event,context) ?? fallback(event);
    const currentGroup=groups.get(original)!;
    const canonical=normalized.has(currentGroup), textEvent=['text_delta','text_snapshot'].includes(event.category);
    if (canonical) updates=updates.filter(action=>action.kind!=='assistant' && (!textEvent || action.kind!=='thinking'));
    if (typeof p.output_text==='string' && (canonical || textEvent || p.delivery_phase==='terminal')) {
      const thinking=/reasoning|thinking/.test(event.native_type || '');
      // A page containing only a native final snapshot already has the full
      // reply. Do not append its separately flushed suffix a second time.
      const nativeFinal=!canonical && !textEvent && actions.some(a=>a.kind==='assistant' && a.id.startsWith(`${epoch}:`));
      if (!nativeFinal) updates.unshift({id:`normalized:${currentGroup}:${thinking?'thinking':'assistant'}`,
        kind:thinking?'thinking':'assistant',title:thinking?'Thinking':'Assistant',text:p.output_text,
        append:event.category!=='text_snapshot'});
    }
    for (const update of updates) {
      update.id=`${epoch}:${update.id}`;
      const index=positions.get(update.id), prior=index===undefined?undefined:actions[index];
      const next: TerminalAction={...prior,...update,title:update.title || prior?.title || 'Tool',time:prior?.time || event.received_at,sequence:prior?.sequence || event.sequence};
      if (update.text!==undefined) next.text=clean(update.append ? (prior?.text || '')+update.text : update.text);
      if (update.output!==undefined) next.output=clean(update.appendOutput ? (prior?.output || '')+update.output : update.output || prior?.output || '');
      if (!update.fields?.length && prior?.fields?.length) next.fields=prior.fields;
      // Empty start frames remain mergeable but never become visible rows.
      if (index===undefined) {positions.set(update.id,actions.length);actions.push(next);} else actions[index]=next;
    }
  }
  return actions.filter(a => a.kind==='status' || a.kind==='error' || a.kind==='approval' ||
    !!a.text?.trim() || !!a.output?.trim() || !!a.fields?.length || a.kind==='tool' && a.title!=='Tool' && !!a.status);
}
