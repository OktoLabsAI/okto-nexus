import type {ConnectionConfiguration, SetupRequest, SetupTest} from './connectionConfiguration';
import {parseConnectionConfiguration} from './connectionConfiguration';
import type {runtimeApi, ConnectionCatalogItem, ProjectPresetOverview, RuntimeOptions, SetupDraftView, SetupFinishResult} from './runtimeApi';

export type ProjectConnectApi = Pick<typeof runtimeApi, 'me' | 'projectPreset' | 'setupDraft' | 'executors' |
  'options' | 'workspacePaths' | 'connectionCatalog' | 'binding' | 'checkLocalInstallation' |
  'testSetup' | 'setupTest' | 'finishSetup' | 'recoverSetup' | 'setupReceipt' | 'connectionWorkspaces'>;
export interface ConnectWorkspace {workspace_id: string; display_name: string | null}
export type ConnectPhase = 'loading' | 'choose' | 'configure' | 'review' | 'checking' | 'testing' | 'finish' | 'uncertain' | 'complete' | 'remote';
export interface ConnectSnapshot {
  phase: ConnectPhase; busy: boolean; error: string; catalog: ConnectionCatalogItem[];
  workspaces: ConnectWorkspace[]; workspace: ConnectWorkspace | null; serverId: string;
  agentId: string; displayName: string; executorId: string; executorLabel: string;
  options: RuntimeOptions | null; candidateRef: string; configuration: ConnectionConfiguration | null;
  preset: ProjectPresetOverview | null; draft: SetupDraftView | null; request: SetupRequest | null;
  test: SetupTest | null; result: SetupFinishResult | null;
  workspacePaths: string[];
  retained: boolean;
  catalogStatus: 'loading' | 'ready' | 'unavailable';
  reviewIdentity: ProjectPresetOverview['identity'] | null; reviewEffects: string[]; nativePolicySource: string | null;
}
interface Checkpoint {
  version: 1; identity: string; server: string; workspace: string | null;
  kind: 'version' | 'test' | 'finish'; agentId: string; displayName: string;
  executorId: string; candidateRef: string; configuration: ConnectionConfiguration;
  request: SetupRequest | null;
  reviewIdentity: ProjectPresetOverview['identity'] | null; reviewEffects: string[]; nativePolicySource: string | null;
}
type StoragePort = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;
const clone = <T,>(value: T): T => JSON.parse(JSON.stringify(value)) as T;
function freeze<T>(value: T): T {
  if (value && typeof value === 'object') {Object.freeze(value);Object.values(value).forEach(freeze);}
  return value;
}
function code(error: unknown): string {return error && typeof error === 'object' && 'code' in error ? String(error.code) : '';}
const message = (error: unknown) => error instanceof Error ? error.message : String(error);
const newId = (prefix: string) => prefix + Array.from(crypto.getRandomValues(new Uint8Array(16)), n => n.toString(16).padStart(2,'0')).join('');
const MAX_PAGES=32;
const identityFields=['server_id','executor_id','binding_id','endpoint_id','agent_id','workspace_id','workspace_binding_id'] as const;
function identifier(value:unknown):value is string{return typeof value==='string'&&value.length>0&&value.length<=160&&!/[\u0000-\u001f\u007f]/.test(value);}
function sameScope(value:Record<string,string>,expected:Record<string,string>){return value!==null&&typeof value==='object'&&!Array.isArray(value)&&Object.keys(value).sort().join('|')===Object.keys(expected).sort().join('|')&&Object.keys(expected).every(key=>value[key]===expected[key]);}

export function connectCheckpointKey(identity: string, server: string, workspace: string | null) {
  return 'okto-nexus:project-connect:v1:' + [identity, server, workspace || 'new-project'].map(encodeURIComponent).join(':');
}
function safeConfiguration(value: ConnectionConfiguration) {
  if(value.format!=='okto-nexus-connection'||value.version!==1)throw new Error('A complete reviewed host configuration is required.');
  // Reuse the existing portable-format validation, preserving this host's
  // reviewed destinations rather than adopting its deliberately reset export.
  parseConnectionConfiguration(JSON.stringify(value));
  if (Object.values(value.secret_bindings).some(ref => !/^(vault|provider):\S+$/.test(ref))) throw new Error('Only protected secret references can be retained.');
  if(Object.keys(value.harness_settings).some(key=>/(api.?key|token|password|secret|credential|environment|^env$)/i.test(key)))
    throw new Error('Credentials and environment secrets are not retained by this flow.');
  return clone(value);
}
export function connectorDraftCommand(origin: string, shell: 'powershell' | 'posix') {
  const url = new URL(origin);
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash ||
      !['', '/'].includes(url.pathname) || ['localhost','[::1]','0.0.0.0'].includes(url.hostname) || /^127\./.test(url.hostname))
    throw new Error('Use the Server address reachable from the Connector host; localhost refers to that host.');
  const quote = (text: string) => shell === 'powershell' ? "'"+text.replace(/['\u2018\u2019\u201a\u201b]/g, x => x+x)+"'" : "'"+text.replace(/'/g,"'\"'\"'")+"'";
  return `okto-nexus-connector connect --server=${quote(url.origin)} --setup-draft ${quote('HOST_DRAFT.json')}`;
}

/** Orchestrates existing services. A catalog row or draft is never authority. */
export class ProjectConnectModel {
  private state: ConnectSnapshot;
  private listeners = new Set<() => void>();
  private controller = new AbortController();
  private revision = 0;
  private me: {server_id: string; agent_id: string} | null = null;
  private checkpoint: Checkpoint | null = null;
  constructor(private api: ProjectConnectApi, private storage: StoragePort,
      private identity: string, workspace: ConnectWorkspace | null, private makeId = newId) {
    if (!identity) throw new Error('The authenticated dashboard identity is required.');
    this.state = {phase:'loading',busy:false,error:'',catalog:[],workspaces:[],workspace,serverId:'',
      agentId:'',displayName:'',executorId:'',executorLabel:'',options:null,candidateRef:'',configuration:null,
      preset:null,draft:null,request:null,test:null,result:null,workspacePaths:[],retained:false,catalogStatus:'loading',reviewIdentity:null,reviewEffects:[],nativePolicySource:null};
  }
  getSnapshot = () => this.state;
  subscribe = (fn: () => void) => {this.listeners.add(fn);return () => this.listeners.delete(fn);};
  dispose() {this.revision++;this.controller.abort();this.listeners.clear();}
  private set(value: Partial<ConnectSnapshot>) {if (!this.controller.signal.aborted) {this.state={...this.state,...value};this.listeners.forEach(fn => fn());}}
  private key() {return connectCheckpointKey(this.identity, this.state.serverId, this.state.workspace?.workspace_id || null);}
  private async run(action: () => Promise<void>, uncertain = false) {
    const revision = this.revision;
    this.set({busy:true,error:''});
    try {await action();} catch (error) {
      if (revision === this.revision && !this.controller.signal.aborted) this.set({error:message(error),...(uncertain ? {phase:'uncertain' as const} : {})});
    } finally {if(revision===this.revision)this.set({busy:false});}
  }
  private assertEditable() {
    if (this.checkpoint || this.state.request || this.state.busy) throw new Error('Recover the retained attempt before changing its reviewed selection.');
  }
  async initialize() {await this.run(async () => {
    const me = await this.api.me(this.controller.signal);this.me=me;
    if(!identifier(me.server_id)||!identifier(me.agent_id))throw new Error('The authenticated Server identity is unconfirmed.');
    if(this.controller.signal.aborted)return;
    this.set({serverId:me.server_id});
    const saved=this.storage.getItem(this.key());
    if(saved) {
      const item=JSON.parse(saved) as Checkpoint;
      if(item.version!==1||item.identity!==this.identity||item.server!==me.server_id||item.workspace!==(this.state.workspace?.workspace_id||null))
        throw new Error('This saved setup belongs to another identity, Server or project.');
      safeConfiguration(item.configuration);
      if(item.request?.mcp_preset)throw new Error('MCP material cannot be restored by this short setup flow.');
      if(item.request&&Object.keys(item.request).some(key=>!['client_intent_id','agent_id','executor_id','candidate_ref','inventory_revision','workspace_id','binding_id','baseline','configuration','broadcast_handoff_auto_claim','project_preset','agent_creation','native_decision_policy'].includes(key)))
        throw new Error('The retained request contains unsupported material.');
      if(!['version','test','finish'].includes(item.kind)||typeof item.agentId!=='string'||!item.agentId||
          item.request&&(item.request.agent_id!==item.agentId||item.request.executor_id!==item.executorId||
            item.request.workspace_id!==item.workspace||item.request.candidate_ref!==item.candidateRef||
            JSON.stringify(item.request.configuration)!==JSON.stringify(item.configuration)||item.request.binding_id!==null))
        throw new Error('The retained setup does not match its identity or exact project selection.');
      if(item.request)freeze(item.request);
      if(item.request&&(!item.reviewIdentity||item.reviewIdentity.defaults_hash!==item.request.agent_creation?.defaults_hash))
        throw new Error('The retained identity review does not match its request.');
      this.checkpoint=item;
      this.set({phase:'uncertain',agentId:item.agentId,displayName:item.displayName,executorId:item.executorId,
        candidateRef:item.candidateRef,configuration:item.configuration,request:item.request,retained:true,
        reviewIdentity:item.reviewIdentity,reviewEffects:item.reviewEffects||[],nativePolicySource:item.nativePolicySource,
        error:'A previous attempt is retained. Check its receipt and test status before continuing.'});
      return;
    }
    const preset = await this.api.projectPreset(this.controller.signal);
    const workspaces: ConnectWorkspace[]=[];let after: string|null=null;
    const seen=new Set<string>(),ids=new Set<string>();let complete=false;
    for(let pageNumber=0;pageNumber<MAX_PAGES;pageNumber++) {
      const page=await this.api.connectionWorkspaces(after,this.controller.signal);
      if(!Array.isArray(page.items)||page.items.length>100||typeof page.has_more!=='boolean')throw new Error('The project directory is unconfirmed.');
      let previous=after;
      for(const item of page.items){
        if(!item||Object.keys(item).some(key=>!['workspace_id','display_name'].includes(key))||!identifier(item.workspace_id)||ids.has(item.workspace_id)||
            item.display_name!==null&&typeof item.display_name!=='string'||previous!==null&&item.workspace_id<=previous)
          throw new Error('The project directory contains an invalid or repeated project reference.');
        ids.add(item.workspace_id);workspaces.push({workspace_id:item.workspace_id,display_name:item.display_name});
        previous=item.workspace_id;
      }
      if(!page.has_more){if(page.next_workspace_id!==null)throw new Error('The project continuation is invalid.');complete=true;break;}
      if(!identifier(page.next_workspace_id)||seen.has(page.next_workspace_id)||!page.items.length||page.next_workspace_id!==page.items.at(-1)?.workspace_id)
        throw new Error('The project directory changed. Reload it.');
      seen.add(page.next_workspace_id);after=page.next_workspace_id;
    }
    if(!complete)throw new Error('The project directory exceeds the complete interactive page budget. No partial directory is used.');
    if(this.state.workspace&&!ids.has(this.state.workspace.workspace_id))throw new Error('The selected project is no longer available.');
    this.set({preset,workspaces});
    await this.catalog();this.set({phase:'choose'});
  });}
  private async catalog() {
    this.set({catalog:[],catalogStatus:'loading'});
    const items: ConnectionCatalogItem[]=[];const seen=new Set<string>(),ids=new Set<string>();let cursor:string|null=null,revision:string|null=null,total:number|null=null,complete=false;
    const scope:Record<string,string>=this.state.workspace?{workspace_id:this.state.workspace.workspace_id}:{};
    try {
      for(let pageNumber=0;pageNumber<MAX_PAGES;pageNumber++) {
        const page=await this.api.connectionCatalog(scope,cursor,this.controller.signal);
        if(page.version!==1||page.server_id!==this.me?.server_id||!sameScope(page.scope,scope)||!Array.isArray(page.items)||page.items.length>100||
            typeof page.has_more!=='boolean'||!Number.isSafeInteger(page.total)||page.total<0||page.total_is_exact!==true||
            page.requires_canonical_revalidation!==true||page.cursor_integrity!=='unsigned_scope_checked'||typeof page.revision!=='string'||!/^[0-9a-f]{64}$/.test(page.revision))
          throw new Error('The complete scoped connection catalog is unconfirmed.');
        if(revision!==null&&page.revision!==revision||total!==null&&page.total!==total)throw new Error('The connection catalog changed. Reload it.');
        revision=page.revision;total=page.total;
        for(const item of page.items){
          if(!item||identityFields.some(key=>!identifier(item[key]))||item.server_id!==this.state.serverId||
              this.state.workspace&&item.workspace_id!==this.state.workspace.workspace_id||!['local','remote'].includes(item.execution_location)||item.needs_revalidation!==true||
              !identifier(item.adapter_id)||!identifier(item.activation_state)||
              [item.binding_revision,item.realization_revision,item.endpoint_revision].some(value=>!Number.isSafeInteger(value)||value<1)||
              [item.endpoint_enabled,item.agent_active,item.executor_revoked].some(value=>typeof value!=='boolean')||
              [item.agent_label,item.workspace_label,item.host_label].some(value=>value!==null&&(typeof value!=='string'||value.length>120)))
            throw new Error('The connection catalog contains a foreign or invalid context.');
          const key=item.server_id+':'+item.binding_id;if(ids.has(key))throw new Error('The connection catalog repeats a binding.');ids.add(key);
          items.push({server_id:item.server_id,binding_id:item.binding_id,executor_id:item.executor_id,endpoint_id:item.endpoint_id,
            workspace_binding_id:item.workspace_binding_id,agent_id:item.agent_id,workspace_id:item.workspace_id,adapter_id:item.adapter_id,
            binding_revision:item.binding_revision,realization_revision:item.realization_revision,endpoint_revision:item.endpoint_revision,
            activation_state:item.activation_state,endpoint_enabled:item.endpoint_enabled,agent_active:item.agent_active,executor_revoked:item.executor_revoked,
            execution_location:item.execution_location,agent_label:item.agent_label,workspace_label:item.workspace_label,host_label:item.host_label,needs_revalidation:true});
        }
        if(!page.has_more){if(page.next_cursor!==null||items.length!==total)throw new Error('The connection catalog is incomplete.');complete=true;break;}
        if(items.length>=total)throw new Error('The connection continuation contradicts its total.');
        if(typeof page.next_cursor!=='string'||!page.next_cursor||page.next_cursor.length>2048||seen.has(page.next_cursor)||!page.items.length)
          throw new Error('The connection catalog has an invalid continuation. Reload it.');
        seen.add(page.next_cursor);cursor=page.next_cursor;
      }
      if(!complete)throw new Error('The connection catalog exceeds its complete page budget. Select a narrower project scope.');
      this.set({catalog:items,catalogStatus:'ready'});
    }catch(error){this.set({catalog:[],catalogStatus:'unavailable'});throw error;}
  }
  async refreshCatalog(){this.assertEditable();await this.run(()=>this.catalog());}
  async selectWorkspace(workspace: ConnectWorkspace|null) {
    if(workspace&&!this.state.workspaces.some(item=>item.workspace_id===workspace.workspace_id))throw new Error('Choose a project from the complete authorized directory.');
    this.assertEditable();this.set({workspace,options:null,candidateRef:'',workspacePaths:[],catalog:[],catalogStatus:'loading',
      ...(this.state.configuration?{configuration:{...this.state.configuration,workspace_root:'',workspace_label:workspace?.display_name||'Project'}}:{})});
    await this.run(async()=>{await this.catalog();if(this.state.executorId){await this.loadOptions();await this.loadPaths();}});
  }
  async resume(item: ConnectionCatalogItem): Promise<ConnectionCatalogItem|null> {
    let result:ConnectionCatalogItem|null=null;
    await this.run(async()=>{
      const selected=this.state.catalog.find(row=>identityFields.every(key=>row[key]===item[key]));
      if(this.state.catalogStatus!=='ready'||!selected)
        throw new Error('Reload the complete authorized catalog before selecting this connection.');
      if(item.server_id!==this.state.serverId||this.state.workspace&&item.workspace_id!==this.state.workspace.workspace_id)
        throw new Error('This connection belongs to another Server or project.');
      const binding=await this.api.binding(item.binding_id);
      if(this.controller.signal.aborted)return;
      if(binding.server_id!==item.server_id||binding.binding_id!==item.binding_id||binding.agent_id!==item.agent_id||
          binding.executor_id!==item.executor_id||binding.workspace_id!==item.workspace_id||binding.workspace_binding_id!==item.workspace_binding_id||
          binding.adapter_id!==item.adapter_id||binding.binding_revision!==item.binding_revision||binding.realization_revision!==item.realization_revision)
        throw new Error('This connection changed. Reload its canonical record.');
      result=selected;
    });return result;
  }
  remote() {this.assertEditable();this.set({phase:'remote'});}
  choose() {this.assertEditable();this.set({phase:'choose'});}
  async add() {this.assertEditable();await this.run(async()=>{
    if(this.state.catalogStatus!=='ready')throw new Error('Confirm the complete project connection catalog before adding another harness.');
    if(!this.me||!this.state.preset)throw new Error('The project recommendation is not loaded.');
    const agent=this.makeId('project_');
    const draft=await this.api.setupDraft(agent,this.controller.signal);
    const executors=await this.api.executors(this.me.agent_id,this.controller.signal);
    const local=executors.filter(item=>item.kind==='embedded');
    if(local.length!==1)throw new Error('This Server has no unique local executor. Use the Connector on its execution host.');
    const configuration:ConnectionConfiguration={format:'okto-nexus-connection',version:1,adapter_id:'',execution_location:'local',
      workspace_root:'',workspace_label:this.state.workspace?.display_name||'Project',provider_home:null,secret_bindings:{},alias:'',automatic_reply:true,
      ...clone(this.state.preset.configuration)};
    this.set({phase:'configure',agentId:agent,draft,executorId:local[0].executor_id,executorLabel:local[0].label||'Nexus Server',configuration});
    await this.loadOptions();
    await this.loadPaths();
  });}
  private async loadPaths() {
    if(!this.state.workspace||!this.state.configuration)return;
    const paths=await this.api.workspacePaths(this.state.workspace.workspace_id,this.state.executorId,this.controller.signal);
    this.set({workspacePaths:paths.items.map(item=>item.path),...(paths.items.length===1?{
      configuration:{...this.state.configuration,workspace_root:paths.items[0].path}}:{})});
  }
  private async loadOptions() {
    if(!this.me)throw new Error('The authenticated Server identity is unavailable.');
    // Canonical TerminalConnection.options uses the existing caller identity for
    // inventory while a proposed project identity remains uncreated.
    const me=await this.api.me(this.controller.signal);
    if(me.server_id!==this.state.serverId)throw new Error('The Server installation changed.');
    this.set({options:await this.api.options(me.agent_id,this.state.executorId,this.state.workspace?.workspace_id||'',this.controller.signal)});
  }
  selectInstallation(candidateRef:string) {
    this.assertEditable();const option=this.state.options?.options.find(item=>item.candidate_ref===candidateRef);
    if(!option?.can_configure||!this.state.configuration||this.state.options?.freshness!=='FRESH')throw new Error('Select an eligible installation from current Server evidence.');
    const label=this.state.options?.catalog.runtimes.find(item=>item.adapter_id===option.adapter_id)?.display_name||'Project assistant';
    const count=this.state.catalog.filter(item=>item.adapter_id===option.adapter_id&&item.workspace_id===this.state.workspace?.workspace_id).length;
    const name=(label+(count?' '+(count+1):'')+' — '+(this.state.workspace?.display_name||this.state.configuration.workspace_label||'Project')).slice(0,120);
    this.set({candidateRef,displayName:name,configuration:{...this.state.configuration,adapter_id:option.adapter_id,
      alias:name,provider_home:option.provider_home_suggestion||null,harness_settings:{...this.state.preset!.configuration.harness_settings}}});
  }
  customize(changes:Partial<ConnectionConfiguration>, displayName=this.state.displayName) {
    this.assertEditable();if(!this.state.configuration)throw new Error('Load the project defaults first.');
    this.set({configuration:safeConfiguration({...this.state.configuration,...changes}),displayName});
  }
  private retain(kind:Checkpoint['kind'],request:SetupRequest|null) {
    if(!this.state.configuration)throw new Error('The reviewed configuration is unavailable.');
    const checkpoint:Checkpoint={version:1,identity:this.identity,server:this.state.serverId,
      workspace:this.state.workspace?.workspace_id||null,kind,agentId:this.state.agentId,displayName:this.state.displayName,
      executorId:this.state.executorId,candidateRef:this.state.candidateRef,configuration:safeConfiguration(this.state.configuration),request:request?clone(request):null,
      reviewIdentity:this.state.reviewIdentity?clone(this.state.reviewIdentity):null,reviewEffects:[...this.state.reviewEffects],nativePolicySource:this.state.nativePolicySource};
    if(request?.mcp_preset)throw new Error('MCP material is not retained by the short connection flow.');
    this.storage.setItem(this.key(),JSON.stringify(checkpoint)); // Failure prevents POST.
    this.checkpoint=checkpoint;this.set({retained:true});
  }
  async verifyInstallation() {this.assertEditable();await this.run(async()=>{
    if(!this.me||!this.state.options||!this.state.candidateRef)throw new Error('Select an observed installation.');
    this.retain('version',null);this.set({phase:'checking'});
    await this.api.checkLocalInstallation(this.state.executorId,{agent_id:this.me.agent_id,
      adapter_id:this.state.configuration!.adapter_id,candidate_ref:this.state.candidateRef,
      inventory_revision:this.state.options.inventory_revision,approved:true});
    await this.loadOptions();
    this.versionConfirmed();
  },true);}
  private versionConfirmed() {
    if(this.controller.signal.aborted)return;
    const choice=this.state.options?.options.find(item=>item.candidate_ref===this.state.candidateRef);
    if(this.state.options?.freshness!=='FRESH'||choice?.technical_state!=='READY_FOR_RUNTIME')throw new Error('Installation confirmation is still unavailable. Recover the same check.');
    this.storage.removeItem(this.key());this.checkpoint=null;this.set({phase:'configure',retained:false});
  }
  review() {
    this.assertEditable();const {draft,preset,configuration:c,options}=this.state;
    const choice=options?.options.find(item=>item.candidate_ref===this.state.candidateRef);
    if(!draft||!preset||!c||options?.freshness!=='FRESH'||!choice?.can_configure||choice.technical_state!=='READY_FOR_RUNTIME')throw new Error('Verify this eligible installation before reviewing the connection.');
    if(!c.workspace_root.trim()||!c.workspace_label.trim()||!this.state.displayName.trim()||this.state.displayName.length>120)throw new Error('Choose the Server project folder and a collaborator name.');
    if(c.execution_location!=='local'||c.runtime_enabled!==true)throw new Error('New project identities require the reviewed local managed connection.');
    const native=draft.native_decision_policy;
    if(!native||!native.value&&!native.can_initialize)throw new Error('The Server native decision policy must be reviewed by its operator before this project setup.');
    const request:SetupRequest={client_intent_id:this.makeId('setup_'),agent_id:this.state.agentId,
      executor_id:this.state.executorId,candidate_ref:this.state.candidateRef,inventory_revision:options.inventory_revision,
      workspace_id:this.state.workspace?.workspace_id||null,binding_id:null,baseline:clone(draft.baseline),
      configuration:safeConfiguration(c),project_preset:clone(preset.origin),
      agent_creation:{display_name:this.state.displayName.trim(),defaults_hash:draft.agent_creation_defaults.defaults_hash},
      broadcast_handoff_auto_claim:false,native_decision_policy:{expected_revision:native.revision,initialize:native.can_initialize}};
    this.set({phase:'review',request:freeze(request),reviewIdentity:clone(draft.agent_creation_defaults),reviewEffects:[...preset.effects],nativePolicySource:native.source});
  }
  editReview() {if(this.checkpoint||this.state.busy)throw new Error('Recover the submitted attempt before editing.');this.set({phase:'configure',request:null});}
  async test(approved:boolean) {
    if(!approved||this.state.phase!=='review'||!this.state.request)throw new Error('Review and explicitly consent to the model test first.');
    await this.run(async()=>{this.retain('test',this.state.request);this.set({phase:'testing'});
      const test=await this.api.testSetup(this.state.request!);this.validateTest(test,this.state.request!);this.set({test,phase:test.status==='succeeded'?'finish':test.status==='failed'?'uncertain':'testing'});
    },true);
  }
  async recover() {await this.run(async()=>{
    if(!this.checkpoint)throw new Error('There is no retained attempt to recover.');
    if(this.checkpoint.kind==='version') {
      const [draft,preset]=await Promise.all([this.api.setupDraft(this.state.agentId,this.controller.signal),this.api.projectPreset(this.controller.signal)]);
      this.set({draft,preset});await this.catalog();await this.loadOptions();this.versionConfirmed();return;
    }
    const request=this.checkpoint.request;
    if(!request)throw new Error('The retained request is unavailable.');
    if(this.checkpoint.kind==='finish') {
      try {const receipt=await this.api.recoverSetup(request,this.controller.signal);
        if(receipt.setup_run_id!==request.client_intent_id||receipt.state!=='committed'||!/^sha256:[0-9a-f]{64}$/.test(receipt.request_hash))throw new Error('The recovered receipt belongs to another setup or has an invalid request reference.');
        this.complete(receipt.result);return;}
      catch(error){if(code(error)!=='NOT_FOUND')throw error;}
    }
    const test=await this.api.setupTest(request.client_intent_id,this.controller.signal);
    this.validateTest(test,request);
    this.set({test,phase:test.status==='succeeded'?'finish':test.status==='running'?'testing':'uncertain'});
  },true);}
  async checkTest() {await this.run(async()=>{
    if(!this.state.request)throw new Error('The retained test ID is unavailable.');
    const test=await this.api.setupTest(this.state.request.client_intent_id,this.controller.signal);
    this.validateTest(test,this.state.request);
    this.set({test,phase:test.status==='succeeded'?'finish':test.status==='failed'?'uncertain':'testing'});
  },true);}
  async finish() {
    if(this.state.phase!=='finish'||this.state.test?.status!=='succeeded'||!this.state.request)throw new Error('A successful test of this exact review is required.');
    await this.run(async()=>{this.retain('finish',this.state.request);this.complete(await this.api.finishSetup(this.state.request!));},true);
  }
  async retryReview() {
    if(this.checkpoint?.kind!=='test'||this.state.test?.status!=='failed'||!this.state.test.retryable_failure||this.state.busy)
      throw new Error('Only a known failed test with confirmed cleanup can enter a new review.');
    await this.run(async()=>{
      const id=this.checkpoint!.request!.client_intent_id;
      try {await this.api.setupReceipt(id,this.controller.signal);throw new Error('This setup is committed. Recover its existing receipt.');}
      catch(error){if(code(error)!=='NOT_FOUND')throw error;}
      const [draft,preset]=await Promise.all([this.api.setupDraft(this.state.agentId,this.controller.signal),this.api.projectPreset(this.controller.signal)]);
      this.storage.setItem(this.key()+':previous:'+encodeURIComponent(id),JSON.stringify(this.checkpoint));
      this.storage.removeItem(this.key());this.checkpoint=null;
      this.set({phase:'configure',draft,preset,request:null,test:null,retained:false});
      await this.loadOptions();
    });
  }
  private complete(result:SetupFinishResult) {
    if(this.controller.signal.aborted)return;
    const request=this.state.request,binding=result.binding;
    if(!request||result.saved!==true||result.agent_id!==request.agent_id||result.agent_created!==true||!binding||
        binding.server_id!==this.state.serverId||binding.agent_id!==request.agent_id||binding.executor_id!==request.executor_id||
        binding.adapter_id!==request.configuration.adapter_id||binding.candidate_ref!==request.candidate_ref||
        !identifier(binding.binding_id)||!identifier(binding.workspace_id)||!identifier(binding.workspace_binding_id)||
        request.workspace_id!==null&&binding.workspace_id!==request.workspace_id||result.project_preset&&
        (result.project_preset.id!==request.project_preset?.id||result.project_preset.revision!==request.project_preset?.revision))
      throw new Error('The Server result does not confirm this exact reviewed identity, installation and project. The retained request was preserved.');
    this.storage.removeItem(this.key());this.checkpoint=null;this.set({phase:'complete',result,retained:false});
  }
  private validateTest(test:SetupTest,request:SetupRequest) {
    if(test.test_id!==request.client_intent_id||!['running','succeeded','failed'].includes(test.status)||typeof test.stage!=='string'||
        !Array.isArray(test.details)||test.details.some(value=>typeof value!=='string')||
        test.retryable_failure!==undefined&&typeof test.retryable_failure!=='boolean')
      throw new Error('The returned test does not belong to the retained exact request. No replacement test was started.');
  }
}
