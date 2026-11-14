"""One canonical containment operation; never starts or approves native work."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
PREFIX = '/api/v1/runtime-management'
SESSION = 'ses_8605c3af6fc1ce021f4a6375b94e1e69'
OPERATION = 'op_92b7ca515e9efa6b38b48a5dce51d560'
REQUEST_ID = 'm1v13-cleanup-interrupt-01'
TURN = '01a1dae3-7e69-7183-8eff-29aa5a951752'
SCOPE = {
 'server_id': 'srv_a3f134b449dbffa20c126dae6f9a8aa9',
 'executor_id': 'exe_429348b4147e50ab63d19caa4cd2255c',
 'binding_id': 'bind_2420012e566c1965caa4813e2b6a068a',
 'agent_id': 'm1v12-local', 'workspace_id': 'wsr_8c2e749623fa4c330976cc3be7d9d314',
 'workspace_binding_id': 'wxb_00e22d62fe976f7c3814b0da6ca6746c',
 'session_id': SESSION, 'session_owner_generation': 1, 'authorization_revision': 2,
 'configuration_revision': 2, 'binding_revision': 1, 'credential_epoch': 1}
REQUEST = {k: SCOPE[k] for k in ('agent_id', 'binding_id', 'workspace_binding_id', 'session_id')}
REQUEST.update(client_intent_id=REQUEST_ID, intent='turn.interrupt',
 target={'kind': 'native_turn_id', 'expected_turn_id': TURN})

def require(value, reason):
    if not value:
        raise RuntimeError(reason)

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def read(path):
    return json.loads(Path(path).read_bytes())

def load(name, pin):
    require(sha(pin['path']) == pin['sha256'], 'SOURCE_CHANGED')
    spec = importlib.util.spec_from_file_location(name, pin['path'])
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

def scope(value):
    require(value.get('scope') == SCOPE, 'EXACT_SCOPE_CHANGED')

def metadata(value):
    keys = ('scope', 'operation_id', 'client_intent_id', 'action', 'intent_hash',
            'admission_state', 'receipt_revision', 'possible_effect', 'retry_safe',
            'executor_stage', 'error', 'resolution_revision', 'session_id',
            'can_submit', 'blockers', 'semantic_intent')
    # Result payload/native content is deliberately excluded.
    return {k: value[k] for k in keys if k in value}

def observe(http):
    service = http('GET', '/api/v1/service')['data']
    require(service.get('pid') == 15244 and service.get('generation') == '6397df3a52b4780c6380f733f4ff5223'
        and service.get('state') == 'stopping', 'OWNED_DRAINING_SERVICE_REQUIRED')
    session = http('GET', PREFIX + '/runtime/sessions/' + SESSION + '?executor_id=' + SCOPE['executor_id'])
    scope(session)
    require(session.get('lease_state') in ('ACTIVE', 'REVOKED'), 'LEASE_SCOPE_UNCONFIRMED')
    operation = http('GET', PREFIX + '/runtime/operations/' + OPERATION)
    scope(operation)
    require(operation.get('operation_id') == OPERATION and operation.get('action') == 'turn.submit', 'ORIGINAL_OPERATION_CHANGED')
    return operation

def contain(http, save):
    # Exactly one resolve and at most one admission. No retry/recovery POST.
    save('resolve-reserved', {'request': REQUEST, 'at': time.time()})
    resolved = http('POST', PREFIX + '/runtime/intents:resolve', REQUEST)
    save('resolved', metadata(resolved))
    scope(resolved)
    require(resolved.get('client_intent_id') == REQUEST_ID
        and resolved.get('session_id') == SESSION
        and resolved.get('semantic_intent', {}).get('action') == 'turn.interrupt'
        and resolved.get('semantic_intent', {}).get('target') == REQUEST['target'], 'RESOLUTION_MISMATCH')
    require(resolved.get('can_submit') is True and resolved.get('blockers') == [], 'CONTAINMENT_BLOCKED')
    admission = {k: resolved[k] for k in ('client_intent_id', 'operation_id', 'resolution_revision', 'intent_hash')}
    save('admit-reserved', admission)
    value = http('POST', PREFIX + '/runtime/operations', admission)
    save('admitted', metadata(value))
    scope(value)
    require(value.get('operation_id') == admission['operation_id']
        and value.get('intent_hash') == admission['intent_hash']
        and value.get('action') == 'turn.interrupt', 'ADMISSION_MISMATCH')
    return value

def main():
    p = argparse.ArgumentParser()
    p.add_argument('mode', choices=('preflight', 'execute', 'reconcile'))
    p.add_argument('--manifest-sha256', required=True)
    args = p.parse_args()
    require(sha(HERE / 'manifest.json') == args.manifest_sha256, 'MANIFEST_CHANGED')
    m = read(HERE / 'manifest.json')
    require(sha(__file__) == m['helper_sha256'], 'HELPER_CHANGED')
    common = load('driver_common', m['common'])
    context = common.gate(SimpleNamespace(**m['authority']))
    if args.mode == 'preflight':
        for pin in m['before_pins'].values():
            require(sha(pin['path']) == pin['sha256'], 'PRECONDITION_CHANGED')
        from okto_nexus.adapters.outbound.terminal_http import LocalOperatorHTTP
        print(json.dumps({'state': 'OFFLINE_PREFLIGHT_PASS', 'http_class': LocalOperatorHTTP.__module__}))
        return 0
    ledger = HERE / 'runtime'
    ledger.mkdir(exist_ok=True)
    def save(name, value):
        common.reserve(ledger / (name + '.json'), {**common.tags(context), **value})
    from okto_nexus.adapters.outbound.terminal_http import LocalOperatorHTTP
    http = LocalOperatorHTTP(host='127.0.0.1', port=58631, timeout=10)
    if args.mode == 'reconcile':
        for label, op in [('original', OPERATION), ('containment', read(ledger / 'admit-reserved.json')['operation_id'])]:
            try:
                value = http('GET', PREFIX + '/runtime/operations/' + op)
                scope(value)
                save(label + '-reconciled', metadata(value))
            except Exception as exc:
                save(label + '-reconciliation-unconfirmed', {'error_type': type(exc).__name__, 'code': getattr(exc, 'code', None)})
        return 0
    for pin in m['before_pins'].values():
        require(sha(pin['path']) == pin['sha256'], 'PRECONDITION_CHANGED')
    observer = load('m1_v13_observation', m['observer'])
    handle = observer.PhysicalProcess(15244)
    try:
        require(handle.birth() == 134391461038622963 and not handle.wait(0), 'OWNER_BIRTH_CHANGED')
        current = observe(http)
        require(current.get('admission_state') in ('ACCEPTED', 'DISPATCHED'), 'WORK_ALREADY_TERMINAL_OR_UNKNOWN')
        save('execute-reserved', {'manifest_sha256': args.manifest_sha256,
             'operation_before': metadata(current), 'force_used': False, 'model_admissions': 0,
             'maximum_resolve_posts': 1, 'maximum_operation_posts': 1})
        try:
            value = contain(http, save)
            result = {'state': 'CONTAINMENT_ADMITTED_NOT_YET_SETTLED', 'containment': metadata(value)}
        except Exception as exc:
            result = {'state': 'CONTAINMENT_UNCONFIRMED', 'error_type': type(exc).__name__,
                      'code': getattr(exc, 'code', None), 'possible_effect': getattr(exc, 'possible_effect', None)}
            save('execute-result', result)
            raise
        finally:
            # The supplement never edits campaign accounting or the original product work checkpoint.
            for name, pin in m['before_pins'].items():
                require(sha(pin['path']) == pin['sha256'], 'HISTORY_CHANGED_' + name)
        save('execute-result', result)
        print(json.dumps(result))
    finally:
        handle.close()
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
