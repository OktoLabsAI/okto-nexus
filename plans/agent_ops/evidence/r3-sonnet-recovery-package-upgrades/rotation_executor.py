"""Finite rotation/import exception executor. Real effects require explicit selection."""
from pathlib import Path
import argparse,contextlib,hashlib,importlib.util,io,json,os,sqlite3,sys,time
sys.path.insert(0,str(Path(__file__).resolve().parent))
HERE=Path(__file__).resolve().parent
AGENT='m1-sonnet-remote'
SERVER='srv_a3f134b449dbffa20c126dae6f9a8aa9'
def require(value,code):
    if not value:raise RuntimeError(code)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_bytes())
def pin(item):
    p=Path(item['path']);require(sha(p)==item['sha256'],'PIN_CHANGED');return p
def module(name,item):
    spec=importlib.util.spec_from_file_location(name,pin(item));value=importlib.util.module_from_spec(spec);sys.modules[name]=value;spec.loader.exec_module(value);return value

def check_vault_acl(root,campaign_root):
    import win32api,win32con,win32security,ntsecuritycon
    original=Path(root).absolute();boundary=Path(campaign_root).absolute()
    require(original.is_relative_to(boundary),'VAULT_OUTSIDE_CAMPAIGN')
    cursor=original
    while True:
        require(cursor.exists() and not win32api.GetFileAttributes(str(cursor))&win32con.FILE_ATTRIBUTE_REPARSE_POINT,
            'REPARSE_POINT_REFUSED')
        if cursor==boundary:break
        cursor=cursor.parent
    root=original.resolve();require(root==original,'VAULT_PATH_RESOLUTION_CHANGED');vault=root/'vault'
    token=win32security.OpenProcessToken(win32api.GetCurrentProcess(),win32con.TOKEN_QUERY)
    try:user=win32security.GetTokenInformation(token,win32security.TokenUser)[0]
    finally:token.Close()
    system=win32security.CreateWellKnownSid(win32security.WinLocalSystemSid,None)
    expected={win32security.ConvertSidToStringSid(s) for s in (user,system)}
    result=[]
    for p in (root,vault,vault/'secrets.json'):
        if not p.exists():
            require(p.name=='secrets.json','VAULT_DIRECTORY_REQUIRED');continue
        require(not win32api.GetFileAttributes(str(p))&win32con.FILE_ATTRIBUTE_REPARSE_POINT,'REPARSE_POINT_REFUSED')
        sd=win32security.GetNamedSecurityInfo(str(p),win32security.SE_FILE_OBJECT,win32security.DACL_SECURITY_INFORMATION)
        acl=sd.GetSecurityDescriptorDacl();require(acl is not None and acl.GetAceCount()==2,'EXACT_VAULT_ACL_REQUIRED')
        if p==vault:require(sd.GetSecurityDescriptorControl()[0]&0x1000,'VAULT_DACL_MUST_BE_PROTECTED')
        seen=set()
        for i in range(acl.GetAceCount()):
            hdr,mask,sid=acl.GetAce(i)
            require(hdr[0]==0 and mask==ntsecuritycon.FILE_ALL_ACCESS,'VAULT_ACL_ACCESS_CHANGED')
            seen.add(win32security.ConvertSidToStringSid(sid))
        require(seen==expected,'VAULT_ACL_PRINCIPAL_CHANGED')
        result.append({'name':p.name,'exact_user_system_full_control':True})
    return result

def canonical_epoch(home):
    path=Path(home)/'nexus.db'
    conn=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=1)
    try:
        conn.execute('PRAGMA query_only=ON');deadline=time.monotonic()+2
        conn.set_progress_handler(lambda:int(time.monotonic()>deadline),1000)
        agent=conn.execute('SELECT is_active FROM agents WHERE agent_id=?',(AGENT,)).fetchone()
        revision=conn.execute('SELECT server_id,credential_epoch FROM execution_agent_revisions WHERE agent_id=?',(AGENT,)).fetchone()
        bindings=conn.execute('SELECT count(*) FROM execution_bindings b JOIN agent_endpoints ep ON ep.endpoint_id=b.endpoint_id WHERE b.server_id=? AND ep.agent_id=?',(SERVER,AGENT)).fetchone()[0]
        require(agent==(1,) and revision is not None and revision[0]==SERVER and bindings==0,'CANONICAL_IDENTITY_SCOPE_CHANGED')
        return revision[1]
    finally:conn.close()

def validate_authorization(authority,expected,plaintext_path):
    require(authority.get('rotation_plan_sha256')==expected and authority.get('status')=='SPECIFIC_EXCEPTION_AUTHORIZED'
        and authority.get('agent_id')==AGENT and authority.get('revoke_lost_epoch')==1
        and authority.get('plaintext_file_path')==plaintext_path
        and isinstance(authority.get('user_authorization_reference'),str) and authority['user_authorization_reference'],
        'SPECIFIC_STORAGE_AND_REVOCATION_AUTHORIZATION_REQUIRED')

class Context:
    def __init__(self,plan,expected,authorization_sha):
        require(Path(plan).resolve()==HERE/'rotation-plan.json' and sha(plan)==expected,'ROTATION_PLAN_CHANGED')
        self.P=read(plan);self.plan_sha=expected;self.authorization_sha=authorization_sha
        require(self.P['agent_id']==AGENT and self.P['server_id']==SERVER and self.P['max_rotation_attempts']==1,'ROTATION_SCOPE_CHANGED')
        for item in self.P['runtime_pins'].values():pin(item)
        for item in self.P['basis'].values():pin(item)
        require(sha(self.P['authorization_receipt'])==authorization_sha,'AUTHORIZATION_RECEIPT_CHANGED')
        authority=read(self.P['authorization_receipt'])
        validate_authorization(authority,expected,self.P['plaintext_file_path'])
        lifecycle=module('sonnet_recovery_context',self.P['lifecycle_context'])
        lp=self.P['lifecycle_plan'];self.base=lifecycle.RecoveryContext(pin(lp),lp['sha256'])
        self.PUBLIC,self.PRIVATE,self.ROOT=self.base.PUBLIC,self.base.PRIVATE,self.base.ROOT
        for name in ('server_home','connector_state','operator_home'):
            require(Path(self.P['paths'][name]).resolve()==Path(self.base.P['paths'][name]).resolve(),'OWN_RECOVERY_PATH_CHANGED')
        require(Path(self.P['plaintext_file_path']).resolve()==Path(self.P['paths']['connector_state']).resolve()/'vault/secrets.json','OWN_VAULT_PATH_CHANGED')
        self.python=self.P['python'];require(Path(self.python).resolve()==Path(self.base.python).resolve(),'LIFECYCLE_PACKAGE_CHANGED')
        require(Path(sys.prefix).resolve()==Path(self.python).parent.parent.resolve(),'NEW_PACKAGE_PREFIX_REQUIRED')
    def save(self,name,value):
        self.base.save(name,dict(value,rotation_plan_sha256=self.plan_sha,authorization_receipt_sha256=self.authorization_sha))
    def state(self):
        from okto_nexus_connector.storage.state_store import StateStore
        from okto_nexus_connector.platform.paths import state_file
        return StateStore(state_file(Path(self.P['paths']['connector_state']))).load()
    def preflight(self,phase):
        require(phase in ('producer','consumer','before_transfer'),'ROTATION_PHASE_INVALID')
        self.base.require_ready()
        check_vault_acl(self.P['paths']['connector_state'],self.ROOT)
        state=self.state();require(not state.identities and not state.bindings,'EMPTY_OWN_IDENTITY_STATE_REQUIRED')
        require(state.preferences.get('vault.fallback_file.approved') is True,'FALLBACK_NOT_PREAPPROVED')
        require(not Path(self.P['plaintext_file_path']).exists(),'UNEXPECTED_EXISTING_SECRET_FILE')
        if phase!='consumer':require(canonical_epoch(self.P['paths']['server_home'])==1,'EXPECTED_EPOCH_ONE_CHANGED')
        else:require((self.PUBLIC/'rotation-post-reserved.json').exists(),'ROTATION_RESERVATION_REQUIRED')
        return True
    def consumer_env(self):
        env=self.base.connector_env();env['OKTO_NEXUS_CONNECTOR_VAULT']='file';return env

def approve_storage(X):
    # This is separate from the credential channel, after specific user selection.
    X.base.require_ready()
    require(not X.state().identities,'EMPTY_OWN_IDENTITY_STATE_REQUIRED')
    root=Path(X.P['paths']['connector_state']);require(not (root/'vault/secrets.json').exists(),'UNEXPECTED_EXISTING_SECRET_FILE')
    X.save('storage-consent-reserved.json',{'plaintext':True,'path':X.P['plaintext_file_path'],'credential_read':False})
    helper=module('sonnet_recovery_acl',X.P['acl_helper']);helper.secure_directory(root/'vault',root)
    from okto_nexus_connector.cli.commands.identity import _approve_fallback
    from okto_nexus_connector.storage.state_store import StateStore
    from okto_nexus_connector.platform.paths import state_file
    from types import SimpleNamespace
    old=sys.stdin
    try:
        sys.stdin=io.StringIO('yes\n')
        with contextlib.redirect_stderr(io.StringIO()),contextlib.redirect_stdout(io.StringIO()):
            approved=_approve_fallback(SimpleNamespace(non_interactive=False,credential_stdin=False),None,StateStore(state_file(root)))
    finally:sys.stdin=old
    require(approved is True,'STORAGE_CONSENT_NOT_RECORDED')
    X.save('storage-consent-result.json',{'approved':True,'plaintext':True,'path':X.P['plaintext_file_path'],
        'acl':check_vault_acl(root,X.ROOT),'credential_read':False,'http_calls':0})

def transfer(X,transfer_once):
    X.preflight('before_transfer')
    X.save('rotation-transfer-reserved.json',{'status':'RESERVED_BEFORE_PRODUCER','max_rotation_attempts':1,'provider_turns':0})
    argv=[X.python,'-I','-B','-X','utf8',str(pin(X.P['runtime_pins']['rotation_producer.py'])),
        '--plan',str(HERE/'rotation-plan.json'),'--expected-plan-sha256',X.plan_sha,'--authorization-sha256',X.authorization_sha]
    consumer=[X.python,'-I','-B','-X','utf8','-m','okto_nexus_connector.cli.main','--non-interactive','--json',
        '--state-dir',X.P['paths']['connector_state'],'identity','add','--server',X.P['origin'],
        '--alias',AGENT,'--agent',AGENT,'--credential-stdin']
    deadline=time.monotonic()+120
    def guard(phase):
        require(time.monotonic()<deadline,'TRANSFER_DEADLINE_EXPIRED');return X.preflight(phase)
    value=transfer_once(producer_argv=argv,consumer_argv=consumer,env=X.base.env(),consumer_env=X.consumer_env(),
        cwd=X.ROOT,timeout_seconds=120,synthetic_probe=False,effect_guard=guard,deadline_monotonic=deadline)
    fields=('status','producer_exit','consumer_exit','active_job_processes_after','forced_owned_cleanup',
        'effect_guard_required','effect_gates_allowed','public_ipc_readers_joined')
    public={k:value.get(k) for k in fields}
    X.save('rotation-protected-transfer-result.json',public)
    require(public['status']=='TRANSFERRED_ONCE' and public['producer_exit']==public['consumer_exit']==0
        and public['active_job_processes_after']==0 and public['forced_owned_cleanup'] is False
        and public['effect_guard_required'] is True and public['effect_gates_allowed']==['producer','consumer']
        and public['public_ipc_readers_joined'] is True,'ROTATION_IMPORT_UNCONFIRMED_NO_RETRY')
    identity=X.state().identity_by_alias(AGENT)
    require(identity is not None and identity.agent_id==AGENT and identity.server_id==SERVER
        and type(identity.credential_epoch) is int and identity.credential_epoch==2
        and identity.revoked is False,'IMPORTED_IDENTITY_UNCONFIRMED')
    require(canonical_epoch(X.P['paths']['server_home'])==2,'NEW_CREDENTIAL_EPOCH_UNCONFIRMED')
    X.base.require_ready()
    X.save('rotation-import-result.json',{'status':'ROTATED_ONCE_IMPORTED_ONCE','agent_id':AGENT,'server_id':SERVER,
        'old_epoch':1,'current_epoch':2,'rotation_post_count':1,'consumer_count':1,'protected_transfer':public,
        'acl':check_vault_acl(X.P['paths']['connector_state'],X.ROOT),'original_transfer_preserved_unconfirmed':True,
        'old_profile_replayed':False,'provider_turns':0})

def load_context(producer=False):
    p=argparse.ArgumentParser();p.add_argument('--plan',required=True);p.add_argument('--expected-plan-sha256',required=True)
    p.add_argument('--authorization-sha256',required=True)
    if not producer:p.add_argument('action',choices=('approve-storage','transfer'))
    a=p.parse_args();X=Context(a.plan,a.expected_plan_sha256,a.authorization_sha);X.action=getattr(a,'action',None);return X

def main():
    X=load_context()
    if X.action=='approve-storage':approve_storage(X)
    else:
        for item in X.P['protected_dependencies'].values():pin(item)
        helper=module('sonnet_rotation_protected_pty',X.P['protected_transfer']);transfer(X,helper.transfer_once)
    print(json.dumps({'status':'COMPLETED','action':X.action,'provider_turns':0}));return 0
if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as error:
        print(json.dumps({'status':'ROTATION_RECOVERY_UNCONFIRMED','error_type':type(error).__name__,'automatic_retry':False}))
        raise SystemExit(3) from None
