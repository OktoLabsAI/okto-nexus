import { content, fields, object, string, tool, type HarnessAdapter } from './model';

export const codexAdapter: HarnessAdapter = {
  id: 'codex_app_server',
  matches: e => /^(item\/|turn\/|thread\/)/.test(e.native_type || ''),
  adapt(event, context) {
    const p = object(event.payload), type = event.native_type || '';
    const item = object(p.item), itemType = string(item.type);
    const id = `codex:${context.turn}:${string(item.id || p.itemId) || event.sequence}`;
    if (type === 'item/agentMessage/delta') return [{id, kind:'assistant', title:'Assistant', text:string(p.delta || p.output_text), append:true}];
    if (/item\/reasoning\/.+Delta$/.test(type)) return [{id, kind:'thinking', title:'Thinking', text:string(p.delta), append:true}];
    if (type === 'item/commandExecution/outputDelta') return [{id,kind:'tool',title:'Command',output:string(p.delta),appendOutput:true}];
    if (type === 'item/started' || type === 'item/completed') {
      const status = type.endsWith('completed') ? string(item.status) || 'completed' : 'running';
      if (itemType === 'agentMessage') return [{id,kind:'assistant',title:'Assistant',text:string(item.text)}];
      if (itemType === 'userMessage') return [{id,kind:'user',title:'You',text:content(item.content)}];
      if (itemType === 'reasoning') return [{id,kind:'thinking',title:'Thinking',text:content(item.summary || item.content)}];
      if (itemType === 'commandExecution') return [tool(id,'Command',{command:item.command, directory:item.cwd},item.aggregatedOutput,status)];
      if (itemType === 'mcpToolCall' || itemType === 'dynamicToolCall') return [tool(id,
        [item.server,item.tool].filter(Boolean).join(' · ') || 'Tool',item.arguments,item.error || item.result,status)];
      if (itemType === 'fileChange') return [{id,kind:'tool',title:'File changes',fields:fields(item.changes),status}];
      if (itemType === 'webSearch') return [tool(id,'Web search',{query:item.query},item.action,status)];
      if (itemType) return [{id,kind:'tool',title:itemType,fields:fields(Object.fromEntries(Object.entries(item).filter(([k])=>!['id','type','status'].includes(k)))),status}];
      return [];
    }
    if (/tokenUsage|thread\/started|reasoning\/.*Added/.test(type)) return [];
    return null;
  },
};
