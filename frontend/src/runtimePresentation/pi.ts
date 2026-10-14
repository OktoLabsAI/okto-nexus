import { content, object, string, tool, type HarnessAdapter } from './model';

export const piAdapter: HarnessAdapter = {
  id:'pi_rpc',
  matches:e => /^(agent_|turn_|message_|tool_execution_|extension_ui_)/.test(e.native_type || ''),
  adapt(event, context) {
    const p=object(event.payload), type=event.native_type || '';
    if (type==='turn_start') return [];
    if (type==='extension_ui_request' && p.method==='setStatus') return string(p.statusText || p.text)
      ? [{id:`pi:status:${string(p.statusKey) || event.sequence}`,kind:'status',title:'Harness status',text:string(p.statusText || p.text)}] : [];
    if (type==='message_start') {context.message=`message-${++context.serial}`;context.messageFinished=false;return [];}
    const id=`pi:${context.turn}:${context.message}`, delta=object(p.assistantMessageEvent);
    if (type==='message_update') {
      if (delta.type==='text_delta') return [{id,kind:'assistant',title:'Assistant',text:string(delta.delta || p.output_text),append:true}];
      if (delta.type==='thinking_delta') return [{id:`${id}:thinking`,kind:'thinking',title:'Thinking',text:string(delta.delta),append:true}];
      return [];
    }
    if (type==='message_end' || type==='turn_end') {
      const message=object(p.message);
      if (type==='turn_end' && context.messageFinished) return [];
      context.messageFinished=true;
      if (message.stopReason==='error') return [{id:`${id}:error`,kind:'error',title:'Execution failed',text:string(message.errorMessage) || 'The harness ended the response with an error.'}];
      if (message.stopReason==='aborted') return [{id:`${id}:aborted`,kind:'status',title:'Response interrupted'}];
      if (message.role==='toolResult') return [{id:`pi:tool:${string(message.toolCallId)}`,kind:'tool',title:string(message.toolName),output:content(message.content),status:message.isError?'failed':'completed'}];
      if (message.role==='user') return [{id:`user:${event.sequence}`,kind:'user',title:'You',text:content(message.content)}];
      const blocks=Array.isArray(message.content)? message.content : [];
      const text=blocks.filter(b=>object(b).type==='text').map(b=>string(object(b).text)).join('') || string(p.output_text);
      return [{id,kind:'assistant',title:'Assistant',text}];
    }
    if (/^tool_execution_/.test(type)) {
      const call=`pi:tool:${string(p.toolCallId) || event.sequence}`;
      if (type==='tool_execution_start') return [tool(call,p.toolName,p.args,undefined,'running')];
      return [{id:call,kind:'tool',title:string(p.toolName),output:content(p.result || p.partialResult),status:type==='tool_execution_end'?(p.isError?'failed':'completed'):'running'}];
    }
    if (type==='agent_end') return [];
    return null;
  },
};
