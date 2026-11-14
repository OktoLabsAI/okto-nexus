"""One explicit expired-grant replacement through installed work authorize CLI."""
from pathlib import Path
from datetime import datetime, timezone
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from driver_common import Refused, gate, main_guard, parser, public_save, read_json, require, require_tags, sha
from adopt_local import check_canonical
from m1_v13_observation import status, same_owner

ACTIONS = {'open', 'send', 'steer', 'interrupt', 'close'}
SCOPE = ('server_id', 'executor_id', 'binding_id', 'workspace_binding_id', 'agent_id', 'workspace_id', 'endpoint_id')
PREFIX = '/api/v1/runtime-management'


def validate_review(context, review, *, allow_available=False):
    expected = context.P['adoption']['expected_scope']
    grants = review.get('current_grants')
    require(review.get('state') == 'authorization_review'
        and review.get('has_more_grants') is False and review.get('total_grants') == 1
        and isinstance(grants, list) and len(grants) == 1
        and review.get('scope') == {k: expected[k] for k in SCOPE}, 'EXACT_EXPIRED_GRANT_REVIEW_REQUIRED')
    grant = grants[0]
    require(grant.get('state') in ({'expired', 'available'} if allow_available else {'expired'})
        and review.get('can_issue') is (grant.get('state') == 'expired') and grant.get('used_executions') == 0
        and grant.get('max_executions') == 20 and isinstance(grant.get('expires_at'), str)
        and set(grant.get('actions', [])) == ACTIONS == set(review.get('actions', [])),
        'UNUSED_EXPIRED_GRANT_REQUIRED')
    request = review['request']
    require(request.get('binding_id') == expected['binding_id'] and request.get('max_executions') == 20
        and isinstance(request.get('expected_revision'), str) and bool(request['expected_revision'])
        and isinstance(request.get('expires_at'), str) and bool(request['expires_at']), 'GRANT_REQUEST_CHANGED')
    return grant['grant_id']


def bounded_transport(raw, phase, counts, *, expected_request=None):
    """The canonical CLI owns semantics/CAS; this fence forbids unrelated POSTs."""
    allowed = {'review': {'review'}, 'apply': {'recover', 'issue'}}[phase]
    def call(method, path, body=None):
        if method != 'GET':
            name = path.removeprefix(PREFIX + '/connections/authorizations:')
            require(method == 'POST' and name in allowed and counts.get(name, 0) == 0,
                'AUTHORIZATION_EFFECT_OUTSIDE_SELECTION')
            if phase == 'review':
                require(body.get('minutes') == 60 and body.get('max_executions') == 20, 'AUTHORIZATION_LIMIT_CHANGED')
            else:
                require(body == expected_request, 'AUTHORIZATION_REQUEST_CHANGED')
            counts[name] = 1  # lost responses consume the one allowed effect too
        return raw(method, path, body)
    return call


def require_local_work_authorization(context, *, now=None):
    """Local useful-work gate; no renewals and no expiry-to-issuance inference."""
    adoption = read_json(context.PUBLIC / 'adopt-local-result.json'); require_tags(adoption, context)
    require(adoption.get('status') == 'CONFIGURED_PREDECESSOR_ADOPTED'
        and adoption.get('scope') == context.P['adoption']['expected_scope'], 'LOCAL_ADOPTION_REQUIRED')
    review_path = context.PUBLIC / 'authorize-local-review.json'
    observed = read_json(review_path); require_tags(observed, context)
    review = observed['review']; validate_review(context, review, allow_available=True)
    if review['current_grants'][0]['state'] == 'available':
        require(observed.get('status') == 'EXISTING_GRANT_AVAILABLE', 'GRANT_REVIEW_STATE_CHANGED')
        expiry = review['current_grants'][0]['expires_at']
        basis = 'EXISTING_CANONICALLY_AVAILABLE_GRANT'
    else:
        applied = read_json(context.PUBLIC / 'authorize-local-apply.json'); require_tags(applied, context)
        require(applied.get('status') == 'EXPIRED_UNUSED_GRANT_REPLACEMENT_CONFIRMED'
            and applied.get('review_revision') == review['review_revision']
            and applied.get('review_sha256') == sha(review_path)
            and applied.get('client_request_id') == review['request']['client_request_id']
            and applied.get('grant', {}).get('expires_at') == review['request']['expires_at']
            and applied['grant'].get('max_executions') == 20
            and set(applied['grant'].get('actions', [])) == ACTIONS, 'GRANT_REPLACEMENT_REQUIRED')
        expiry = applied['grant']['expires_at']; basis = 'EXPLICIT_EXPIRED_GRANT_REPLACEMENT'
    current = now or datetime.now(timezone.utc)
    remaining = (datetime.fromisoformat(expiry.replace('Z', '+00:00')) - current).total_seconds()
    require(remaining >= 240, 'TWO_WORK_AUTHORIZATION_WINDOW_INSUFFICIENT')
    return {'basis': basis, 'expires_at': expiry, 'remaining_seconds_by_local_clock': remaining,
        'minimum_window_seconds': 240, 'review_sha256': sha(review_path), 'expiry_state_inferred': False}


def dispatch_cli(controller, flow, phase, poll, review=None):
    label = 'authorize-local-' + phase
    options = ['--minutes', '60', '--actions', '20'] if phase == 'review' else ['--review', review['review_revision']]
    handler = 'authorization_review' if phase == 'review' else 'authorize'
    poll()  # fresh accounting before serial worker admission
    controller.schedule_decision(label, lambda: flow._execute('authorize', options, handler))
    while True:
        poll()
        result = controller.take_api_result()
        if result is not None:
            require(result['label'] == label, 'AUTHORIZATION_RESULT_MISMATCH')
            if not result['ok']:
                raise result['error']
            return result['value']
        time.sleep(.2)


def execute(context, phase):
    require_tags(read_json(context.PUBLIC / 'adopt-local-result.json'), context)
    before = status(context, 'nexus')
    sys.path.insert(0, str(context.modules))
    from cli_flow import CLIFlow
    from serial_flow import SerialFlow
    from independent_journal import CanonicalIntentReader, CoreJournalReader
    from history_observers import attach_existing_work
    from publication import poll_and_publish
    from okto_nexus.adapters.inbound.cli.terminal_target import resolve_terminal_target
    from okto_nexus.adapters.inbound.cli.service import resolve_local_service
    from okto_nexus.application.terminal_connection import document_revision
    controller = context.controller(create=False)
    selected, diagnostics, counts = set(), {}, {}
    before_requests = set(controller.data['requests'])
    review = None
    try:
        controller.attach_owner('local', context.P['paths']['server_home'], lambda: selected.add('local'))
        attach_existing_work(controller, campaign_root=context.ROOT,
            server_home=context.P['paths']['server_home'], connector_state=context.P['paths']['connector_state'],
            stop_for_lane=selected.add)
        profile = context.P['execution_bundle']['profiles']['local']
        args = context.C['service_selection_args']
        service = resolve_terminal_target(args, profile, None, resolve_local_service)
        require(service.adapter.home.resolve() == Path(context.P['paths']['server_home']).resolve(), 'AUTHORIZATION_HOME_CHANGED')
        flow = CLIFlow(service, profile, args)
        pending = flow.document.get('authorization')
        if phase == 'review':
            require(pending is None, 'PRIOR_AUTHORIZATION_SELECTION_PRESENT')
        else:
            path = context.PUBLIC / 'authorize-local-review.json'
            evidence = read_json(path); require_tags(evidence, context)
            review = evidence['review']; validate_review(context, review)
            selection = read_json(context.PRIVATE / 'authorize-local-reviewed.json')
            require_tags(selection, context)
            require(selection.get('decision') == 'issue' and selection.get('review_sha256') == sha(path)
                and selection.get('review_revision') == review['review_revision'], 'EXACT_ROOT_REVIEW_REQUIRED')
            require(pending and pending.get('state') == 'review'
                and pending.get('review_revision') == review['review_revision']
                and document_revision(pending['review']) == review['review_revision'], 'AUTHORIZATION_CHECKPOINT_CHANGED')
        flow.call = bounded_transport(flow.call, phase, counts, expected_request=review['request'] if review else None)
        controller.attach_api_flow('local', flow)
        def publish(value):
            path = context.PUBLIC / 'live-accounting.json'; temporary = path.with_suffix('.pending')
            with temporary.open('w', encoding='utf-8') as stream:
                json.dump(value, stream, indent=2); stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, path)
        def poll():
            value = poll_and_publish(controller, publish, diagnostics, None)
            require(value.get('can_admit') is True and not selected, 'AUTHORIZATION_OBSERVATION_FENCED')
            return value
        serial = SerialFlow(controller, flow, 'local', poll)
        binding = serial.binding(); me = serial.api('GET', '/connections/me')
        check_canonical(context.P['adoption']['expected_scope'], binding, me)
        if 'local' not in controller._readers:
            scope = {k: binding[k] for k in ('server_id', 'executor_id', 'binding_id', 'agent_id', 'workspace_id', 'workspace_binding_id')}
            controller.attach_observer('local', CanonicalIntentReader(context.ROOT, context.P['paths']['server_home'],
                server_id=binding['server_id'], actor_id=me['agent_id'], pre_scope=scope),
                CoreJournalReader(context.ROOT, context.P['paths']['server_home'], 'local'))
        flow.expect(binding, me['agent_id'], flow.document.get('session_id'))
        public_save(context, 'authorize-local-' + phase + '-reserved.json', {'state': 'DISPATCH_RESERVED', 'model_admissions': 0})
        controller.fence.arm(time.monotonic() + 120)
        value = dispatch_cli(controller, flow, phase, poll, review)
        same_owner(before, status(context, 'nexus'))
        require(set(controller.data['requests']) == before_requests, 'AUTHORIZATION_MODEL_RESERVATION_CHANGED')
        if phase == 'review':
            validate_review(context, value, allow_available=True)
            require(document_revision({k: v for k, v in value.items() if k != 'review_revision'}) == value['review_revision'],
                'AUTHORIZATION_REVIEW_HASH_CHANGED')
            available = value['current_grants'][0]['state'] == 'available'
            observed = datetime.now(timezone.utc)
            expiry = datetime.fromisoformat(value['current_grants'][0]['expires_at'].replace('Z', '+00:00'))
            remaining = (expiry - observed).total_seconds()
            output = {'status': 'EXISTING_GRANT_AVAILABLE' if available else 'EXPIRED_UNUSED_GRANT_REVIEWED',
                'review': value, 'observed_at_utc': observed.isoformat(),
                'remaining_seconds_by_local_clock': remaining,
                'two_work_window_seconds': 240, 'two_work_window_available': available and remaining >= 240,
                'expiry_state_source': 'CANONICAL_REVIEW', 'repeat_review_allowed': False}
        else:
            require(value.get('state') == 'authorization_committed', 'AUTHORIZATION_COMMIT_UNCONFIRMED')
            grant = value['result']['grant']
            output = {'status': 'EXPIRED_UNUSED_GRANT_REPLACEMENT_CONFIRMED',
                'client_request_id': value['client_request_id'], 'request_hash': value['request_hash'],
                'grant': {k: grant.get(k) for k in ('grant_id', 'expires_at', 'max_executions', 'actions')},
                'review_revision': review['review_revision'], 'review_sha256': sha(context.PUBLIC / 'authorize-local-review.json')}
        output.update(model_admissions=0, calls=counts, cli_execution=flow.diagnostics(),
            checkpoint_summary=controller.summary(), publication_diagnostics=diagnostics)
        public_save(context, 'authorize-local-' + phase + '.json', output)
        return output
    except BaseException as error:
        selected.add('local'); controller.fault('AUTHORIZATION_MAINTENANCE_UNCONFIRMED')
        public_save(context, 'authorize-local-' + phase + '-unconfirmed.json',
            {'error_type': type(error).__name__, 'model_admissions': 0, 'replay_allowed': False, 'calls': counts})
        raise Refused('AUTHORIZATION_MAINTENANCE_UNCONFIRMED') from None
    finally:
        controller.drain_api()
        if 'local' in selected and not (context.PUBLIC / 'lifecycle-nexus-stop.json').exists():
            public_save(context, 'authorization-normal-stop-reserved.json', {'component': 'nexus', 'force': False})
            child = subprocess.Popen(context.stop_argv('nexus'), cwd=context.CONTROL, env=context.env(),
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            while child.poll() is None:
                try: controller.poll()
                except BaseException: pass
                time.sleep(.2)
        controller.close()


def main():
    p = parser(); p.add_argument('phase', choices=['review', 'apply'])
    args = p.parse_args()
    print(json.dumps(execute(gate(args), args.phase)), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main_guard(main))
