"""One canonical recovery of the campaign-only expired operator account.

inspect is read-only. execute must be explicitly selected by Root after review.
No credential input/output files; a generated password lives only in memory.
"""
from pathlib import Path
from contextlib import closing
import argparse,hashlib,json,os,secrets,sqlite3,subprocess,sys,time
from urllib.request import Request,ProxyHandler,HTTPRedirectHandler,build_opener
HERE=Path(__file__).parent
PLAN=HERE/'operator-recovery-plan.json'
def require(ok,code):
    if not ok:raise RuntimeError(code)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def pin(p):require(sha(p['path'])==p['sha256'],'PIN_CHANGED');return Path(p['path'])
def save(name,value):
    p=HERE/'operator-recovery-public'/name
    with p.with_suffix('.writing').open('x',encoding='utf-8') as f:
        json.dump(value,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
    p.with_suffix('.writing').rename(p)
def inspect(P):
    profile=read(P['operator_profile_path'])
    require({k:profile.get(k) for k in ('format','origin','server_id','username')}==P['operator_metadata'],'OPERATOR_PROFILE_CHANGED')
    db=Path(P['auth_db']);require(db.is_file(),'OWN_AUTH_DB_ABSENT')
    with closing(sqlite3.connect(db.as_uri()+'?mode=ro',uri=True,timeout=5)) as c:
        c.execute('pragma query_only=on')
        accounts=c.execute('SELECT id,username FROM account LIMIT 2').fetchall()
        active=c.execute('SELECT COUNT(*) FROM sessions WHERE expires>?',(time.time(),)).fetchone()[0]
    require(accounts==[(1,P['operator_metadata']['username'])],'DEDICATED_ACCOUNT_CHANGED')
    require(active==0,'ACTIVE_OPERATOR_SESSIONS_REFUSE_RECOVERY')
    private=HERE/'paid-work/private';request=P['request_id']
    require(not (private/(request+'-reserved.json')).exists() and not (private/(request+'-admission.json')).exists(),'PAID_ADMISSION_ALREADY_RESERVED')
    sys.path.insert(0,str(HERE));from sonnet_usage import restore_budget
    budget=restore_budget(read(private/'sonnet-budget.json'))
    require(budget.known==144004 and sum(len(x.reserved) for x in budget.sessions.values())==2,'CARRY_CHANGED')
    return {'account_id':1,'username':accounts[0][1],'active_sessions':active,'known_tokens':144004,'charged_requests':2,'useful05_reserved':False,'useful05_admitted':False,'operator_metadata':P['operator_metadata']}
class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*a,**kw):return None
def account(P,password):
    origin=P['operator_metadata']['origin']
    body=json.dumps({'username':P['operator_metadata']['username'],'password':password}).encode()
    req=Request(origin+'/api/v1/operator-auth/account',data=body,method='POST',headers={'Origin':origin,'X-Nexus-UI':'1','Content-Type':'application/json'})
    with build_opener(ProxyHandler({}),NoRedirect()).open(req,timeout=30) as response:raw=response.read(65537)
    require(len(raw)<=65536,'ACCOUNT_RESPONSE_TOO_LARGE');value=json.loads(raw)
    require(value.get('ok') is True and value.get('data',{}).get('configured') is True,'ACCOUNT_CHANGE_UNCONFIRMED_NO_RETRY')
def execute(P):
    require(Path(sys.executable).resolve()==Path(P['python']).resolve(),'Q_PYTHON_REQUIRED')
    for value in P['pins'].values():pin(value)
    lifecycle=read(pin(P['lifecycle_plan']));L=Path(P['lifecycle_plan']['path']).parent
    for value in lifecycle['runtime_pins'].values():pin(value)
    sys.path.insert(0,str(L));from recovery_context import RecoveryContext
    X=RecoveryContext(P['lifecycle_plan']['path'],P['lifecycle_plan']['sha256'])
    before=inspect(P);X.require_ready()
    public=HERE/'operator-recovery-public';public.mkdir(exist_ok=True)
    save('selection-reserved.json',{'state':'SELECTED_CANONICAL_ACCOUNT_RECOVERY_ONCE','plan_sha256':sha(PLAN),'preflight':before,'provider_calls':0})
    password=secrets.token_urlsafe(36)
    try:
        X.require_ready();inspect(P)
        save('account-reserved.json',{'post_count':1,'username':P['operator_metadata']['username'],'provider_calls':0})
        account(P,password)
        save('account-returned.json',{'configured':True,'account_post_count':1,'session_revocation_selected':True,'password_retained':False})
        X.require_ready()
        save('login-reserved.json',{'login_cli_count':1,'profile':P['operator_metadata']['username']})
        child=subprocess.Popen(P['login_argv'],cwd=X.ROOT,env=X.env(),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
        output,_=child.communicate((password+'\n').encode())
        password=None
        require(child.returncode==0 and len(output)<=65536,'LOGIN_CLI_UNCONFIRMED_NO_RETRY')
        signed=json.loads(output)
        for k,v in [('state','authenticated'),('profile',P['operator_metadata']['username']),('origin',P['operator_metadata']['origin']),('server_id',P['operator_metadata']['server_id'])]:require(signed.get(k)==v,'LOGIN_IDENTITY_CHANGED')
        child=subprocess.Popen(P['status_argv'],cwd=X.ROOT,env=X.env(),stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
        output,_=child.communicate();require(child.returncode==0 and len(output)<=65536,'SESSION_STATUS_UNCONFIRMED')
        status=json.loads(output)
        for k in ('state','profile','origin','server_id'):require(status.get(k)==signed.get(k),'SESSION_STATUS_CHANGED')
        X.require_ready()
        result={'status':'CANONICAL_DEDICATED_OPERATOR_REAUTHENTICATED','account_post_count':1,'login_cli_count':1,'operator':{k:status[k] for k in ('state','profile','origin','server_id')},'provider_calls':0,'password_retained':False,'auth_database_raw_or_hash_published':False,'paid_retry_executed':False}
        save('result.json',result);return result
    finally:password=None
def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=('inspect','execute'));p.add_argument('--expected-plan-sha256',required=True);a=p.parse_args()
    require(sha(PLAN)==a.expected_plan_sha256,'PLAN_CHANGED');P=read(PLAN)
    try:result=inspect(P) if a.action=='inspect' else execute(P)
    except Exception as e:
        # Never print traceback, request/response bodies, cookies or credentials.
        code=str(e) if type(e) is RuntimeError and str(e).replace('_','').isalnum() else type(e).__name__
        print(json.dumps({'state':'REFUSED_OR_UNCONFIRMED','code':code,'automatic_retry':False}));return 1
    print(json.dumps(result));return 0
if __name__=='__main__':raise SystemExit(main())
