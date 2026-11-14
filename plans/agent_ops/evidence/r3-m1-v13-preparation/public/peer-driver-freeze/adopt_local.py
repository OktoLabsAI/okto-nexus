"""Adopt the closed, configured predecessor without setup or model replay."""
from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from driver_common import gate, main_guard, parser, public_save, read_json, require, require_tags, sha
from m1_v13_observation import status, same_owner


def sources(context):
    adoption = context.P['adoption']
    values = {}
    for name in ('profile_pin', 'setup_result_pin', 'predecessor_closure_pin',
                 'predecessor_checkpoint_pin', 'installation_result_pin'):
        pin = adoption[name]
        require(sha(pin['path']) == pin['sha256'], 'ADOPTION_SOURCE_CHANGED')
        if name in ('profile_pin', 'setup_result_pin'):
            values[name] = read_json(pin['path'])
    profile, result = values['profile_pin'], values['setup_result_pin']
    scope = adoption['expected_scope']
    require(profile.get('state') == 'done' and profile.get('version_check_confirmed') is True
        and profile.get('request', {}).get('client_intent_id') == adoption['setup_client_intent_id']
        and all(profile.get('result', {}).get('binding', {}).get(k) == v for k, v in scope.items()),
        'CONFIGURED_PROFILE_REQUIRED')
    require(result.get('cli_exit') == 0 and result.get('reported_state') == 'configured',
        'PREDECESSOR_SETUP_SUCCESS_REQUIRED')
    return scope


def check_canonical(scope, binding, me):
    require(all(binding.get(k) == v for k, v in scope.items())
        and binding.get('state') == 'APPROVED' and me.get('server_id') == scope['server_id'],
        'ADOPTED_BINDING_CHANGED')


def local_flow(context):
    from okto_nexus.adapters.inbound.cli.terminal_target import resolve_terminal_target
    from okto_nexus.adapters.inbound.cli.service import resolve_local_service
    from okto_nexus.adapters.inbound.cli.work import open_work
    profile = context.P['execution_bundle']['profiles']['local']
    service = resolve_terminal_target(context.C['service_selection_args'], profile, None, resolve_local_service)
    require(service.adapter.home.resolve() == Path(context.P['paths']['server_home']).resolve(), 'ADOPTED_HOME_CHANGED')
    flow = open_work(service, profile)
    if hasattr(flow.call, 'timeout'):
        flow.call.timeout = 10
    raw = flow.call
    def read_only(method, path, body=None):
        require(method == 'GET' and body is None, 'ADOPTION_EFFECT_REFUSED')
        return raw(method, path, body)
    flow.call = read_only
    return flow


def adopt(context, *, observe=status, flow_factory=local_flow):
    require_tags(read_json(context.PUBLIC / 'root-driver-preparation.json'), context)
    require(not (context.PRIVATE / 'controller.json').exists(), 'NEW_CONTROLLER_ALREADY_EXISTS')
    scope = sources(context)
    public_save(context, 'adopt-local-reserved.json', {'state': 'READ_ONLY_ADOPTION_RESERVED', 'model_admissions': 0})
    before = observe(context, 'nexus')
    flow = flow_factory(context)
    binding, me = flow.binding(), flow.api('GET', '/connections/me')
    check_canonical(scope, binding, me)
    same_owner(before, observe(context, 'nexus'))
    sources(context)  # pin stability across canonical observations
    controller = context.controller(create=True)
    try:
        summary = controller.summary()
        require(not controller.data['requests'] and summary['known_observed_tokens'] == 111651,
            'ADOPTION_CHECKPOINT_NOT_FRESH')
    finally:
        controller.close()
    result = {'status': 'CONFIGURED_PREDECESSOR_ADOPTED', 'scope': scope, 'owner': before,
        'predecessor_profile_sha256': context.P['adoption']['profile_pin']['sha256'],
        'predecessor_closure_sha256': context.P['adoption']['predecessor_closure_pin']['sha256'],
        'model_admissions': 0, 'setup_replayed': False, 'canonical_observation': 'GET_ONLY',
        'checkpoint_summary': summary}
    public_save(context, 'adopt-local-result.json', result)
    return result


def main():
    p = parser(); p.add_argument('selection', choices=['once'])
    print(json.dumps(adopt(gate(p.parse_args()))), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main_guard(main))
