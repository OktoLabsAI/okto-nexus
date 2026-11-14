"""Pinned canonical connection helpers; no actions at import."""
from pathlib import Path
import asyncio,copy,hashlib,json,os,secrets,sqlite3,time
from urllib.parse import quote
BASE=Path(__file__).resolve().parent
ROOT=BASE/'case'
PUBLIC=BASE/'public'
PRIVATE=BASE/'private'
PROFILE='svc-t15-final-terminal-only'
VARIABLE='SVC_T15_ONLY_CLI_KEY'
REFERENCE='provider:'+VARIABLE
PREFIX='/api/v1/runtime-management'
CONFIG='cli_auth_credentials_store = "file"\n'
class Refused(RuntimeError):
    pass


def require(value, code):
    if not value:
        raise Refused(code)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


class ObservedHTTP:
    """Bounded GET observation; never retries a POST or unrelated error."""
    def __init__(self,raw,plan,deadline,*,clock=time.monotonic,sleep=time.sleep,record=None):
        self.raw,self.plan,self.deadline,self.clock,self.sleep=raw,plan,deadline,clock,sleep
        self.record=record or self.persist

    @staticmethod
    def persist(value):
        path=PUBLIC/'http-observations.json'
        items=json.loads(path.read_bytes()) if path.exists() else []
        require(len(items)<2048,'HTTP_OBSERVATION_RECORD_LIMIT')
        items.append(value)
        pending=path.with_suffix('.pending')
        with pending.open('w',encoding='utf-8',newline='\n') as stream:
            json.dump(items,stream,indent=2);stream.flush();os.fsync(stream.fileno())
        os.replace(pending,path)

    def __call__(self,method,route,body=None):
        from okto_nexus.application.terminal_connection import ConnectionError
        import re
        require(method in ('GET','POST') and route.startswith(PREFIX+'/'),'HTTP_SCOPE_CHANGED')
        if method=='POST':
            require(sha(self.plan['pins']['native']['path'])==self.plan['pins']['native']['sha256'],
                'APPROVED_NATIVE_BYTES_CHANGED')
        while True:
            remaining=self.deadline-self.clock()
            require(remaining>0,'HTTP_OBSERVATION_DEADLINE')
            self.raw.timeout=min(10,remaining)
            started=self.clock()
            try:
                value=self.raw(method,route,body)
            except ConnectionError as error:
                def safe(value):
                    return value if isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9_.:-]{1,100}',value) else 'UNCONFIRMED'
                self.record({'method':method,'route':route,'status':'ERROR','code':safe(error.code),
                    'stage':safe(error.stage),'possible_effect':error.possible_effect if type(error.possible_effect) is bool else None,
                    'elapsed_seconds':self.clock()-started})
                if method!='GET' or error.code!='SERVER_UNREACHABLE' or error.possible_effect is True:raise
                remaining=self.deadline-self.clock()
                require(remaining>0,'HTTP_OBSERVATION_DEADLINE')
                self.sleep(min(.25,remaining))
            else:
                self.record({'method':method,'route':route,'status':'RETURNED','elapsed_seconds':self.clock()-started})
                require(self.clock()<self.deadline,'HTTP_OBSERVATION_DEADLINE')
                return value


def environment(root, python, native, inherited):
    env = {key: inherited[key] for key in ('SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT') if key in inherited}
    require('SYSTEMROOT' in env, 'SYSTEMROOT_REQUIRED')
    env.update(HOME=str(root / 'profile'), USERPROFILE=str(root / 'profile'),
        CODEX_HOME=str(root / 'profile/.codex'), APPDATA=str(root / 'appdata'),
        LOCALAPPDATA=str(root / 'localappdata'), TEMP=str(root / 'tmp'), TMP=str(root / 'tmp'),
        PYTHONDONTWRITEBYTECODE='1', PYTHONUNBUFFERED='1', OKTO_NEXUS_NO_BANNER='1')
    env['PATH'] = os.pathsep.join((str(Path(python).parent), str(Path(native).parent),
                                  str(Path(env['SYSTEMROOT']) / 'System32')))
    return env


def python_argv(python):
    # -I ignores PYTHONUTF8; the explicit flag also covers Unicode CLI JSON.
    return [str(python), '-I', '-B', '-X', 'utf8']


def probe():
    """CLI-process availability only: never claims the synthetic value is a login."""
    from okto_nexus.application.execution_local_launch import ProviderSecretResolver
    class ForbiddenVault:
        def resolve(self, reference):
            raise AssertionError('VAULT_MUST_NOT_BE_CALLED')
    value = asyncio.run(ProviderSecretResolver(ForbiddenVault()).resolve(REFERENCE))
    require(bool(value) and secrets.compare_digest(value, os.environ.get(VARIABLE, '')), 'SENTINEL_NOT_RESOLVED')
    print(json.dumps({'resolved': True, 'reference': REFERENCE, 'synthetic_not_login': True,
                      'vault_calls': 0, 'unicode_roundtrip': chr(0x2014)}))


def selected_request(review, plan, root):
    require(review.get('state') == 'review', 'CLI_REVIEW_MISSING')
    selected, config = review['selection'], review['request']['configuration']
    require(selected['candidate_ref'] == plan['candidate_ref'] and selected['agent'] == PROFILE,
            'SELECTED_CANDIDATE_CHANGED')
    require(Path(config['provider_home']) == root / 'profile/.codex'
        and Path(config['workspace_root']) == root / 'project', 'SELECTED_PATH_CHANGED')
    require(config['adapter_id'] == 'codex_app_server' and config['harness_settings'] == {}
        and config['secret_bindings'] == {}, 'ORIGINAL_CONFIGURATION_CHANGED')
    require(review['request'].get('broadcast_handoff_auto_claim') is False
        and not review['request'].get('mcp_preset'), 'ADDITIONAL_EFFECT_REFUSED')
    request = copy.deepcopy(review['request'])
    request['client_intent_id'] = 'svc-t15-final-terminal-only-01'
    request['configuration']['secret_bindings'] = {'OPENAI_API_KEY': REFERENCE}
    return request


def validate_test(test):
    require(test.get('test_id') == 'svc-t15-final-terminal-only-01' and test.get('status') == 'failed'
        and 'PROVIDER_AUTH_REQUIRED' in test.get('details', [])
        and test.get('retryable_failure') is True, 'SERVICE_AUTH_FAILURE_UNCONFIRMED')
    return {key: test[key] for key in ('test_id', 'status', 'stage', 'retryable_failure')} | {
        'error_code': 'PROVIDER_AUTH_REQUIRED'}


def retained_data(home):
    exclusions = {'service-installation.json', 'service-control.json', 'nexus.db.service-installation.json'}
    result = {}
    for path in sorted(home.rglob('*')):
        require(not getattr(path.lstat(), 'st_file_attributes', 0) & 0x400, 'REPARSE_REFUSED')
        relative = path.relative_to(home).as_posix()
        if path.is_file() and relative not in exclusions:
            result[relative] = {'sha256': sha(path), 'bytes': path.stat().st_size}
    require(bool(result), 'RETAINED_DATA_EMPTY')
    return result


def journal_proof(home):
    journals = list((home / 'connection-tests').glob('*/journal.db'))
    require(len(journals) == 1, 'JOURNAL_COUNT_UNCONFIRMED')
    path = journals[0]
    require(path.resolve().is_relative_to(home.resolve()) and not path.is_symlink(), 'JOURNAL_SCOPE_CHANGED')
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=.25) as db:
        db.execute('PRAGMA query_only=ON')
        opens = db.execute("SELECT stage,error_code,possible_effect,retry_safe FROM operations_v2 WHERE operation_id='open'").fetchall()
        actions = db.execute("SELECT COUNT(*) FROM operation_actions WHERE action IN ('turn.submit','turn.steer')").fetchone()[0]
        turns = db.execute("SELECT COUNT(*) FROM operations_v2 WHERE operation_id='turn'").fetchone()[0]
    require(opens == [('FAILED', 'PROVIDER_AUTH_REQUIRED', 0, 1)] and actions == turns == 0,
            'PRE_NATIVE_ENV_FAILURE_OR_ZERO_TURN_UNCONFIRMED')
    return {'open_stage': 'FAILED', 'error_code': 'PROVIDER_AUTH_REQUIRED', 'possible_effect': False,
        'retry_safe': True, 'turn_actions': actions, 'turn_receipts': turns,
        'read_after_owner_exit': True, 'journal_sha256': sha(path)}


def setup_case(plan, cli, owner, inspect):
    from okto_nexus.adapters.outbound.terminal_http import LocalOperatorHTTP
    from okto_nexus.application.terminal_connection import TerminalConnection, ConnectionError
    require(sha(plan['pins']['native']['path'])==plan['pins']['native']['sha256'],'APPROVED_NATIVE_BYTES_CHANGED')
    code, presentation = cli('plan', ['connect', '--plan', '--client', 'codex', '--project', str(ROOT / 'project'),
        '--profile', PROFILE, '--new-agent', PROFILE, '--provider-home', str(ROOT / 'profile/.codex'),
        '--candidate-ref', plan['candidate_ref'], '--no-start-at-login', '--no-chat', '--json'])
    require(code == 0 and presentation.get('state') == 'review', 'PLAN_FAILED')
    profile = ROOT / 'nexus-home/terminal/profiles' / (PROFILE + '.json')
    review = json.loads(profile.read_bytes())
    original_profile_sha = sha(profile)
    request = selected_request(review, plan, ROOT)
    http = ObservedHTTP(LocalOperatorHTTP(host='127.0.0.1',port=plan['port'],timeout=10),plan,time.monotonic()+120)
    # This own driver request is distinct from the unchanged CLI review/checkpoint.
    document = copy.deepcopy(review)
    document['request'] = request
    save(PRIVATE / 'reviewed-canonical-request.json', request)
    save(PUBLIC / 'canonical-request-review.json', {'request_sha256': sha(PRIVATE / 'reviewed-canonical-request.json'),
        'original_cli_profile_sha256': original_profile_sha, 'reference': REFERENCE,
        'configuration_delta': 'secret_bindings.OPENAI_API_KEY only; new unique client_intent_id',
        'commit_or_binding_creation_authorized': False})
    if review['version_check_required']:
        me = http('GET', PREFIX + '/connections/me')
        require(me['server_id'] == review['server_id'], 'SERVER_CHANGED')
        check = dict(agent_id=me['agent_id'] if request.get('agent_creation') else request['agent_id'],
            adapter_id='codex_app_server', candidate_ref=request['candidate_ref'],
            inventory_revision=request['inventory_revision'], approved=True)
        save(PUBLIC / 'version-check-reserved.json', {'request': check, 'at': time.time(), 'maximum_posts': 1})
        try:
            http('POST', PREFIX + '/runtime/executors/' + quote(request['executor_id'], safe='') + '/installations:check', check)
        except ConnectionError as error:
            if error.code != 'OUTCOME_UNKNOWN' or error.possible_effect is not True:
                raise
        # Installed canonical bounded GET observer, no additional POST/replay.
        flow = TerminalConnection(http, lambda value: save(PRIVATE / 'version-confirmed.json', value))
        http.deadline=time.monotonic()+120
        flow._confirm_version_check(document, request, http.deadline)
    require(sha(profile) == original_profile_sha, 'CLI_PROFILE_MUTATED')
    current = inspect(timeout=2)
    require(current.get('state') == 'ready' and current.get('ready_for_queries') is True
        and all(current.get(k) == v for k, v in owner.identity.items()) and not owner.exited(), 'OWNER_CHANGED_BEFORE_SETUP')
    # Positive exclusion from persisted service context; no credential value is copied.
    context = json.loads((ROOT / 'nexus-home/service-context.json').read_bytes())
    require(VARIABLE.casefold() not in {key.casefold() for key in context['environment']}, 'SENTINEL_CAPTURED_BY_SERVICE')
    require(not (ROOT / 'profile/.codex/auth.json').exists()
        and (ROOT / 'profile/.codex/config.toml').read_text() == CONFIG, 'EMPTY_PROVIDER_HOME_CHANGED')
    save(PRIVATE / 'submitted-request.json', request)
    save(PUBLIC / 'setup-test-reserved.json', {'request_sha256': sha(PRIVATE / 'submitted-request.json'),
        'client_intent_id': request['client_intent_id'], 'at': time.time(), 'maximum_posts': 1,
        'service_context_sha256': sha(ROOT / 'nexus-home/service-context.json'), 'sentinel_reference_absent': True})
    # One POST only. A lost response is uncertainty; never resend or commit.
    http.deadline=time.monotonic()+120
    test = http('POST', PREFIX + '/connections/setup:test', request)
    deadline = http.deadline
    while time.monotonic() < deadline and (test.get('status') == 'running' or
            test.get('status') == 'failed' and not test.get('retryable_failure')):
        time.sleep(.25)
        test = http('GET', PREFIX + '/connections/setup-tests/' + request['client_intent_id'])
    result = validate_test(test)
    require(sha(profile) == original_profile_sha, 'CLI_PROFILE_CHANGED_AFTER_TEST')
    return result


def matching_candidate(view, plan, expected_ref):
    if view.get('adapter_freshness',{}).get('codex_app_server')!='FRESH':return None
    observations=[row for row in view.get('observations',[]) if row.get('adapter_id')=='codex_app_server']
    if len(observations)!=1 or observations[0].get('state')=='PENDING':return None
    require(observations[0].get('state')=='PRESENT','APPROVED_NATIVE_NOT_PRESENT')
    options=[row for row in view.get('options',[]) if row.get('adapter_id')=='codex_app_server']
    require(len(options)==1,'NATIVE_SELECTION_NOT_UNIQUE')
    selected=options[0]
    require(selected.get('candidate_ref')==expected_ref,'NATIVE_PATH_REFERENCE_CHANGED')
    availability=[row for row in view.get('availability',{}).get('availability',[])
        if row.get('adapter_id')=='codex_app_server']
    require(len(availability)==1 and availability[0].get('candidate_ref')==expected_ref
        and availability[0].get('trust')=='selected','NATIVE_SELECTION_UNTRUSTED')
    require(selected.get('can_configure') is True
        and selected.get('technical_state')==availability[0].get('state'),'NATIVE_NOT_CONFIGURABLE')
    return {'candidate_ref':expected_ref,'inventory_revision':view['inventory_revision'],
        'state':availability[0]['state'],'trust':'selected',
        'server_binary_fingerprint_observed':False,
        'binary_evidence_basis':'Approved local binary hash; canonical public path-derived reference only.'}


def observe_candidate(plan):
    from okto_nexus.adapters.outbound.terminal_http import LocalOperatorHTTP
    from nexus_connector_core.installation import installation_ref
    from okto_nexus.application.terminal_connection import TerminalConnection
    native=Path(plan['pins']['native']['path'])
    require(sha(native)==plan['pins']['native']['sha256'],'APPROVED_NATIVE_BYTES_CHANGED')
    expected_ref=installation_ref('codex_app_server',str(native))
    deadline=time.monotonic()+120
    http=ObservedHTTP(LocalOperatorHTTP(host='127.0.0.1',port=plan['port'],timeout=10),plan,deadline)
    me=http('GET',PREFIX+'/connections/me')
    page=http('GET',PREFIX+'/agents/'+quote(me['agent_id'],safe='')+'/executors?limit=100')
    hosts=[row for row in page['items'] if row['kind']=='embedded']
    require(len(hosts)==1 and page['has_more'] is False,'OWN_EXECUTOR_NOT_UNIQUE')
    # The installed canonical flow constructs the public runtime-options route.
    flow=TerminalConnection(http,lambda _:None)
    request={'agent_id':me['agent_id'],'executor_id':hosts[0]['executor_id'],'workspace_id':None}
    observations=0
    while time.monotonic()<deadline:
        view=flow.options(request,deadline=deadline,server_id=me['server_id'])
        require(view.get('agent_id')==me['agent_id'] and view.get('executor_id')==hosts[0]['executor_id'],
            'RUNTIME_OPTIONS_HOST_CHANGED')
        observations+=1
        selected=matching_candidate(view,plan,expected_ref)
        if selected is not None:
            require(time.monotonic()<deadline,'INVENTORY_WAIT_EXPIRED')
            require(sha(native)==plan['pins']['native']['sha256'],'APPROVED_NATIVE_BYTES_CHANGED')
            save(PUBLIC/'fresh-native-selection.json',selected|{'server_id':me['server_id'],
                'executor_id':hosts[0]['executor_id'],'approved_native_path':str(native),
                'local_binary_sha256':plan['pins']['native']['sha256'],
                'get_observations':observations,'no_post_in_readiness_wait':True})
            return plan|{'candidate_ref':selected['candidate_ref']}
        time.sleep(min(1,max(0,deadline-time.monotonic())))
    raise Refused('INVENTORY_PENDING_OR_STALE_NO_PLAN_SENT')
