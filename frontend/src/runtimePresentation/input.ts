import { content, decoded, fields, object, type ActionUpdate } from './model';

// Format only a recognized transport envelope. Never alter the prompt sent to
// the harness, and keep all delivery metadata available for inspection.
export function userInput(id: string, value: unknown): ActionUpdate {
  const text = Array.isArray(value) ? value.map(block => {
    const b = object(block);
    return ['text', 'input_text'].includes(String(b.type)) ? String(b.text ?? '') : content(block);
  }).join('\n') : typeof value === 'string' ? value : content(value);
  const marker = 'NEXUS DELIVERY:';
  const bindingMarker = '\nNEXUS TRANSPORT BINDING:';
  let envelope: unknown = decoded(text), binding: unknown;
  if (text.startsWith(marker)) {
    const start = text.indexOf('\n');
    const boundary = text.indexOf(bindingMarker, start);
    envelope = decoded(text.slice(start + 1, boundary < 0 ? undefined : boundary));
    if (boundary >= 0) {
      const line = text.indexOf('\n', boundary + 1);
      binding = line >= 0 ? decoded(text.slice(line + 1)) : undefined;
    }
  }
  const data = object(envelope);
  if (typeof data.operation_id !== 'string' || typeof data.workspace_id !== 'string' || !Array.isArray(data.content))
    return {id, kind: 'user', title: 'You', text: content(value)};
  const primary = ['subject', 'from_agent_id', 'to_agent_id', 'sender_agent_id', 'recipient_agent_id', 'workspace_id', 'handoff_id', 'claim_epoch'];
  const metadata = Object.fromEntries(Object.entries(data).filter(([key]) => key !== 'content' && !primary.includes(key)));
  return {
    id, kind: 'user', title: data.intent === 'handoff_execute' ? 'Handoff request' : 'Incoming message',
    text: content(data.content),
    fields: fields(Object.fromEntries(primary.filter(key => data[key] !== undefined).map(key => [key, data[key]]))),
    details: [...fields(metadata), ...fields(binding, 'Transport binding')],
  };
}
