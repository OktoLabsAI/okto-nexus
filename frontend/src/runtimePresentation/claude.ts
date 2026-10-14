import { content, decoded, fields, object, string, tool, type ActionUpdate, type HarnessAdapter } from './model';
import { userInput } from './input';

export const claudeAdapter: HarnessAdapter = {
  id:'claude_stream',
  matches:e => /^(stream_event:|system:|result:|assistant$|user_echo$|control_)/.test(e.native_type || ''),
  adapt(event, context) {
    const p=object(event.payload), type=event.native_type || '', stream=object(p.event);
    if (type==='stream_event:message_start') {
      context.message=string(object(stream.message).id) || `message-${++context.serial}`;
      context.blocks.clear();context.messageFinished=false;return [];
    }
    const id=`claude:${context.turn}:${context.message}`;
    if (type==='stream_event:content_block_start') {
      const b=object(stream.content_block), index=Number(stream.index || 0);
      if (b.type==='tool_use') {
        const call=`claude:tool:${string(b.id) || `${id}:${index}`}`;
        context.blocks.set(index,call);return [tool(call,b.name,b.input,undefined,'running')];
      }
      if (b.type==='text') return [{id,kind:'assistant',title:'Assistant',text:string(b.text)}];
      if (b.type==='thinking') return [{id:`${id}:thinking`,kind:'thinking',title:'Thinking',text:string(b.thinking)}];
      return [];
    }
    if (type==='stream_event:content_block_delta') {
      if (typeof p.text==='string') return [{id,kind:'assistant',title:'Assistant',text:p.text,append:true}];
      const delta=object(stream.delta), call=context.blocks.get(Number(stream.index || 0));
      if (delta.type==='input_json_delta' && call) {
        const input=(context.partialInputs.get(call) || '')+string(delta.partial_json);context.partialInputs.set(call,input);
        const parsed=decoded(input);
        return typeof parsed==='object' && parsed!==null ? [{id:call,kind:'tool',title:'',fields:fields(parsed)}] : [];
      }
      if (delta.type==='thinking_delta') return [{id:`${id}:thinking`,kind:'thinking',title:'Thinking',text:string(delta.thinking),append:true}];
      return [];
    }
    if (type==='assistant') {
      const raw=object(p.raw), message=object(raw.message || p.message);
      if (context.messageFinished) context.message=string(message.id) || `message-${++context.serial}`;
      const messageId=`claude:${context.turn}:${context.message}`;
      const blocks=Array.isArray(message.content) ? message.content : [];
      const actions: ActionUpdate[]=[];
      const text=string(p.text) || blocks.map(b=>object(b).type==='text' ? string(object(b).text) : '').join('');
      if (text) actions.push({id:messageId,kind:'assistant',title:'Assistant',text});
      for (const block of blocks) {
        const b=object(block);
        if (b.type==='tool_use') actions.push(tool(`claude:tool:${string(b.id) || messageId}`,b.name,b.input,undefined,'running'));
      }
      context.messageFinished=true;return actions;
    }
    if (type==='user_echo' || type==='user') {
      const m=object(p.message), blocks=Array.isArray(m.content) ? m.content : [];
      const results=blocks.filter(b=>object(b).type==='tool_result').map(b=>{const r=object(b);return {
        id:`claude:tool:${string(r.tool_use_id)}`,kind:'tool' as const,title:'',output:content(r.content),status:r.is_error?'failed':'completed'};});
      return results.length ? results : [userInput(`user:${event.sequence}`,m.content)];
    }
    // The result snapshot is authoritative and may correct the last text frame.
    if (type==='result:output') return [{id,kind:'assistant',title:'Assistant',text:string(p.text)}];
    if (type==='system:thinking_tokens') return [];
    if (type==='system:status') return string(p.status) ? [{id:`status:${event.sequence}`,kind:'status',title:'Harness status',text:string(p.status)}] : [];
    if (type==='system:permission_denied') return [{id:`claude:tool:${string(p.tool_use_id) || event.sequence}`,kind:'tool',title:string(p.tool_name),status:'failed',output:string(p.message) || 'Tool permission denied'}];
    if (type==='rate_limit_event') {
      const limit=object(p.rate_limit_info);
      return ['rejected','blocked'].includes(string(limit.status)) ? [{id:`limit:${event.sequence}`,kind:'error',title:'Rate limit reached',text:string(limit.rateLimitType)}] : [];
    }
    if (/^stream_event:|^control_response:/.test(type)) return [];
    return null;
  },
};
