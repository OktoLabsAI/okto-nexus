export interface ConnectionConfiguration {
  format: 'okto-nexus-connection'; version: 1;
  adapter_id: string; execution_location: 'local' | 'remote';
  runtime_enabled: boolean | null; session_policy: 'shared' | 'per_sender' | 'per_sender_session' | 'one_shot' | null;
  workspace_root: string; workspace_label: string; provider_home: string | null;
  secret_bindings: Record<string,string>; alias: string; harness_settings: Record<string,string>;
  automatic_reply: boolean; tool_access: 'ask' | 'always_allow';
  authorization: {minutes: number | null; actions: number | null};
}
export const emptyConnection = (): ConnectionConfiguration => ({
  format:'okto-nexus-connection',version:1,adapter_id:'',execution_location:'local',runtime_enabled:true,
  session_policy:null,workspace_root:'',workspace_label:'',provider_home:null,secret_bindings:{},alias:'',
  harness_settings:{},automatic_reply:true,tool_access:'ask',authorization:{minutes:60,actions:20},
});
export function parseConnectionConfiguration(text: string): ConnectionConfiguration {
  if (new TextEncoder().encode(text).length > 65536) throw new Error('The file must be 64 KiB or smaller.');
  let value = JSON.parse(text);
  const destination = ['execution_location','workspace_root','workspace_label','provider_home','secret_bindings'];
  if (value?.version === 2) {
    if (destination.some(key => key in value)) throw new Error('Select folders and the execution host on this machine.');
    value = {...value,version:1,execution_location:'local',workspace_root:'',workspace_label:'',provider_home:null,secret_bindings:{}};
  }
  const base = emptyConnection();
  if (!value || Array.isArray(value) || Object.keys(value).sort().join() !== Object.keys(base).sort().join() ||
      value.format !== base.format || value.version !== 1 || !['local','remote'].includes(value.execution_location) ||
      (value.runtime_enabled !== null && typeof value.runtime_enabled !== 'boolean') || typeof value.automatic_reply !== 'boolean' ||
      !['shared','per_sender','per_sender_session','one_shot',null].includes(value.session_policy) || !['ask','always_allow'].includes(value.tool_access))
    throw new Error('Use a complete Okto Nexus connection configuration (version 1).');
  for (const key of ['adapter_id','workspace_root','workspace_label','alias'])
    if (typeof value[key] !== 'string' || value[key].length > 4096) throw new Error(`Invalid ${key}.`);
  if (value.provider_home !== null && typeof value.provider_home !== 'string') throw new Error('Invalid login directory.');
  for (const key of ['harness_settings','secret_bindings']) {
    if (!value[key] || Array.isArray(value[key]) || typeof value[key] !== 'object' || Object.values(value[key]).some(v => typeof v !== 'string')) throw new Error(`Invalid ${key}.`);
  }
  if (Object.values(value.secret_bindings).some(v => !/^(vault|provider):\S+$/.test(String(v)))) throw new Error('Use protected secret references only.');
  if (!value.authorization || Object.keys(value.authorization).sort().join() !== 'actions,minutes') throw new Error('Invalid authorization limits.');
  for (const [key, max] of [['minutes',1440],['actions',1000]] as const) {
    const n = value.authorization[key];
    if (n !== null && (!Number.isInteger(n) || n < 1 || n > max)) throw new Error(`Invalid ${key} limit.`);
  }
  // Legacy exports may contain host paths. Never import them onto another host.
  return {...value,automatic_reply:true,execution_location:'local',workspace_root:'',workspace_label:'',provider_home:null,secret_bindings:{}};
}
export function exportConnectionConfiguration(value: ConnectionConfiguration): string {
  const {execution_location,workspace_root,workspace_label,provider_home,secret_bindings,...portable}=value;
  return JSON.stringify({...portable,automatic_reply:true,version:2},null,2)+'\n';
}
export type SetupBaseline = Record<string,number | null>;
export function sameConnectionConfiguration(left: ConnectionConfiguration, right: ConnectionConfiguration): boolean {
  const canonical = (value: unknown): string => {
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      return JSON.stringify(Object.keys(value).sort().map(key => [key, canonical((value as Record<string, unknown>)[key])]));
    }
    return JSON.stringify(value);
  };
  return canonical(left) === canonical(right);
}
export interface SetupRequest {
  client_intent_id: string; agent_id: string; executor_id: string; candidate_ref: string;
  inventory_revision: string; workspace_id: string | null; binding_id: string | null;
  baseline: SetupBaseline; configuration: ConnectionConfiguration;
  mcp_preset?: {expected_revision: number; servers: import('./api').MCPPreset['servers']};
}
export interface SetupTest {test_id: string; status: 'running' | 'succeeded' | 'failed'; stage: string; details: string[]}

// Remote onboarding and MCP-only changes save policy, not a local installation.
export function policyOnlySetup(request: SetupRequest): SetupRequest {
  const {mcp_preset, ...policy} = request;
  return {...policy, executor_id:'', candidate_ref:'', inventory_revision:'', workspace_id:null, binding_id:null,
    baseline:{...request.baseline,binding_revision:null,endpoint_revision:null}};
}
