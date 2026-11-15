"""Qualified bootstrap primitives; explicit new own operator alias, no model call."""
from pathlib import Path
import json, secrets, subprocess, time
from urllib.request import Request, ProxyHandler, HTTPRedirectHandler, build_opener
from request_context import require, public_save
from reused_observation import endpoint,status,same_owner
class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None

def http(origin, method, route, body, deadline):
    remaining = deadline - time.monotonic()
    require(remaining > 0, 'OPERATOR_PHASE_DEADLINE')
    require(route in ('/api/v1/operator-auth/status', '/api/v1/operator-auth/account'), 'OPERATOR_ROUTE_INVALID')
    headers = {'Origin': origin, 'X-Nexus-UI': '1', 'Content-Type': 'application/json'}
    request = Request(origin + route, data=None if body is None else json.dumps(body).encode(),
        headers=headers, method=method)
    # No inherited proxy, cookies, redirects, forwarded headers, or personal auth.
    with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=min(10, remaining)) as response:
        raw = response.read(65537)
    require(len(raw) <= 65536, 'OPERATOR_RESPONSE_TOO_LARGE')
    return json.loads(raw)

def cli(context, argv, secret, deadline, *, popen=subprocess.Popen):
    require(time.monotonic() < deadline, 'OPERATOR_PHASE_DEADLINE')
    child = popen(argv, cwd=context.ROOT, env=context.env(), stdin=subprocess.PIPE if secret is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    # Keep the exact child handle until exit, even if the observation fence closes.
    # No repeat login, timeout-kill, password argv/env/file, or terminal-text log.
    output, _ = child.communicate(None if secret is None else (secret + '\n').encode())
    require(child.returncode == 0 and time.monotonic() < deadline, 'OPERATOR_CLI_UNCONFIRMED')
    require(len(output) <= 65536, 'OPERATOR_CLI_OUTPUT_TOO_LARGE')
    return json.loads(output)

def commands(context):
    p = context.P
    origin = p['topology']['origin']
    host, port = endpoint(context)
    require(origin == f'http://{host}:{port}', 'OPERATOR_ORIGIN_INVALID')
    account = p['operator_bootstrap']
    name = p['execution_bundle']['operator_profile']
    require(account['username'] == name == 'm1-sonnet-human'
        and Path(account['home']).resolve() == Path(p['paths']['operator_home']).resolve(), 'OPERATOR_ACCOUNT_SCOPE_CHANGED')
    base = [p['package_pins']['python'], '-I', '-B', '-X', 'utf8', '-m', 'okto_nexus.adapters.inbound.cli.main', 'operator']
    profile = ['--profile', name]
    home = ['--home', p['paths']['operator_home']]
    login = base + ['login'] + profile + ['--server', origin, '--username', name, '--password-stdin'] + home
    verify = base + ['status'] + profile + home
    return origin, name, login, verify

def bootstrap(context, expected_server_id, *, effect_guard, deadline_monotonic,
              request=http, run_cli=cli, observe=status, password_factory=lambda: secrets.token_urlsafe(36)):
    origin, username, login, verify = commands(context)
    require(isinstance(expected_server_id, str) and bool(expected_server_id), 'OPERATOR_SERVER_ID_REQUIRED')
    require(not (Path(context.P['paths']['operator_home']) / 'terminal/operators' / (username + '.json')).exists(),
        'OPERATOR_PROFILE_ALREADY_EXISTS')
    for name in ('operator-account-reserved.json', 'operator-login-reserved.json', 'operator-bootstrap-result.json'):
        require(not (context.PUBLIC / name).exists(), 'OPERATOR_REPLAY_REFUSED')
    before = observe(context, 'nexus')
    initial = request(origin, 'GET', '/api/v1/operator-auth/status', None, deadline_monotonic)
    require(initial.get('ok') is True and initial.get('data', {}).get('configured') is False
        and initial['data'].get('local') is True, 'FRESH_LOCAL_ACCOUNT_REQUIRED')
    password = password_factory()
    require(type(password) is str and 12 <= len(password) <= 1024, 'TEMPORARY_PASSWORD_INVALID')
    same_owner(before, observe(context, 'nexus'))
    public_save(context, 'operator-account-reserved.json', {'state': 'DISPATCH_RESERVED',
        'origin': origin, 'username': username, 'owner': before, 'model_admissions': 0})
    require(effect_guard('producer'), 'ACCOUNT_FENCE_CLOSED')
    lost_response = False
    try:
        created = request(origin, 'POST', '/api/v1/operator-auth/account',
            {'username': username, 'password': password}, deadline_monotonic)
    except (OSError, ValueError):
        # Only read reconciliation, while the same original password is in memory.
        lost_response = True
        created = request(origin, 'GET', '/api/v1/operator-auth/status', None, deadline_monotonic)
    require(created.get('ok') is True and created.get('data', {}).get('configured') is True,
        'ACCOUNT_CREATE_UNCONFIRMED')
    if lost_response:
        require(created['data'].get('local') is True, 'ACCOUNT_RECONCILIATION_NOT_LOCAL')
    same_owner(before, observe(context, 'nexus'))
    public_save(context, 'operator-login-reserved.json', {'state': 'DISPATCH_RESERVED',
        'origin': origin, 'username': username, 'server_id': expected_server_id, 'model_admissions': 0})
    require(effect_guard('consumer'), 'LOGIN_FENCE_CLOSED')
    signed = run_cli(context, login, password, deadline_monotonic)
    password = None
    for value in (signed, run_cli(context, verify, None, deadline_monotonic)):
        require(value.get('state') == 'authenticated' and value.get('origin') == origin
            and value.get('server_id') == expected_server_id and value.get('profile') == username,
            'OPERATOR_LOGIN_IDENTITY_UNCONFIRMED')
    same_owner(before, observe(context, 'nexus'))
    return {'status': 'OPERATOR_AUTHENTICATED', 'origin': origin, 'server_id': expected_server_id,
        'profile': username, 'account_post_count': 1, 'login_cli_count': 1, 'lost_create_response': lost_response,
        'model_admissions': 0, 'secret_material_published': False}
