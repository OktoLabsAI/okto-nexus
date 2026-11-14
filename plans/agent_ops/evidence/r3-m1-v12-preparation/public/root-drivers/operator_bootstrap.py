"""One own-server account and canonical login; no model admission or secret log."""
from pathlib import Path
import json
import os
import secrets
import subprocess
import sys
import time
from urllib.request import Request, ProxyHandler, HTTPRedirectHandler, build_opener

sys.path.insert(0, str(Path(__file__).resolve().parent))
from driver_common import Refused, gate, main_guard, parser, public_save, read_json, require, require_tags
from m1_v12_observation import endpoint, status, same_owner


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
    require(account['username'] == name == 'm1v12-human'
        and Path(account['home']).resolve() == Path(p['paths']['operator_home']).resolve(), 'OPERATOR_ACCOUNT_SCOPE_CHANGED')
    base = [p['package_pins']['python'], '-I', '-B', '-m', 'okto_nexus.adapters.inbound.cli.main', 'operator']
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
        require(not (context.ROOT / 'public' / name).exists(), 'OPERATOR_REPLAY_REFUSED')
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


def execute(context):
    require_tags(read_json(context.ROOT / 'public/root-driver-preparation.json'), context)
    require((context.ROOT / 'private/controller.json').is_file(), 'EXISTING_CONTROLLER_REQUIRED')
    origin, _, login, verify = commands(context)
    recipe = read_json(context.P['execution_bundle']['files']['remote_canonical_recipe']['path'])
    require(recipe.get('format') == 'm1-v12-readonly-remote-recipe' and recipe.get('proposal_revision') == 12
        and recipe['limits']['policy'] == context.P['controller_preparation']['policy']
        and recipe['operator_bootstrap']['login']['argv'] == login
        and recipe['operator_bootstrap']['verify_login_argv'] == verify
        and recipe['operator_bootstrap']['read_first']['url'] == origin + '/api/v1/operator-auth/status'
        and recipe['operator_bootstrap']['create_once']['url'] == origin + '/api/v1/operator-auth/account',
        'OPERATOR_RECIPE_SCOPE_CHANGED')
    # Context gate already checked each pin. Import only pinned bundle modules.
    sys.path.insert(0, str(context.modules))
    sys.path.insert(0, str(Path(context.P['execution_bundle']['files']['context']['path']).parent))
    from history_observers import attach_existing_work
    from publication import poll_and_publish
    from remote_transfer_monitor import transfer_with_monitor
    controller = context.controller(create=False)
    selected = set()
    stop_children = []
    diagnostics = {}
    outcome = None
    monitor = None
    try:
        controller.attach_owner('local', context.P['paths']['server_home'], lambda: selected.add('local'))
        attached = attach_existing_work(controller, campaign_root=context.ROOT,
            server_home=context.P['paths']['server_home'], connector_state=context.P['paths']['connector_state'],
            stop_for_lane=selected.add)
        require(attached == ['local'], 'LOCAL_HISTORY_REQUIRED_BEFORE_OPERATOR')
        ids = {r['scope']['server_id'] for r in controller.data['requests'].values()
            if r['kind'] == 'work' and r['lane'] == 'local'}
        require(len(ids) == 1, 'LOCAL_SERVER_ID_UNCONFIRMED')
        def publish(value):
            path = context.ROOT / 'public/live-accounting.json'
            pending = path.with_suffix('.pending')
            with pending.open('w', encoding='utf-8') as stream:
                json.dump(value, stream, indent=2); stream.flush(); os.fsync(stream.fileno())
            os.replace(pending, path)
        def poll():
            value = poll_and_publish(controller, publish, diagnostics, None)
            if value.get('can_admit') is not True:
                selected.add('local')
            return value
        result, monitor = transfer_with_monitor(controller=controller, poll=poll, timeout_seconds=120,
            transfer=lambda **kwargs: bootstrap(context, next(iter(ids)), **kwargs))
        require(monitor['worker_joined'] and monitor['ordered_effect_gates_passed']
            and not monitor['fence_selected'] and result.get('status') == 'OPERATOR_AUTHENTICATED',
            'OPERATOR_BOOTSTRAP_UNCONFIRMED')
        outcome = dict(result, monitor=monitor, historical_lanes_attached=attached, publication_diagnostics=diagnostics)
        public_save(context, 'operator-bootstrap-result.json', outcome)
        return outcome
    except BaseException as error:
        selected.add('local')
        controller.fault('OPERATOR_BOOTSTRAP_UNCONFIRMED')
        public_save(context, 'operator-bootstrap-unconfirmed.json', {'status': 'OPERATOR_BOOTSTRAP_UNCONFIRMED',
            'error_type': type(error).__name__, 'monitor': monitor, 'replay_allowed': False,
            'secret_material_published': False, 'new_model_admissions': 0})
        raise Refused('OPERATOR_BOOTSTRAP_UNCONFIRMED') from None
    finally:
        # transfer_with_monitor retains and joins its worker, hence no login child
        # remains here. Only the existing canonical normal-stop wrapper is used.
        try:
            if 'local' in selected and not (context.ROOT / 'public/lifecycle-nexus-stop.json').exists():
                public_save(context, 'operator-normal-stop-reserved.json', {'component': 'nexus', 'force': False})
                stop_children.append(subprocess.Popen(context.stop_argv('nexus'), cwd=context.ROOT,
                    env=context.env(), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)))
            for child in stop_children:
                while child.poll() is None:
                    try: controller.poll()
                    except BaseException: pass
                    time.sleep(.2)
        finally:
            controller.close()


def main():
    p = parser(); p.add_argument('selection', choices=['once'])
    context = gate(p.parse_args())
    result = execute(context)
    print(json.dumps(result), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main_guard(main))
