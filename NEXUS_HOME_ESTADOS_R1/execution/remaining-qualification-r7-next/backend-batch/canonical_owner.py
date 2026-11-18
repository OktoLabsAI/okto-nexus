"""Prepared canonical owner for functional tests; importing starts nothing.

Bindings/grants/open/turns/requests/interrupt/close use the real application and
Core. Only the subprocess protocol peer is synthetic. No authority SQL writes.
"""
import importlib
import json
import os
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace


def wait(predicate, message, seconds=30):
    deadline = time.monotonic() + seconds
    while True:
        value = predicate()
        if value:
            return value
        assert time.monotonic() < deadline, message
        time.sleep(.03)


class Owner:
    def __init__(self, setup, patch, control, protocol, source):
        self.setup, self.patch, self.control = setup, patch, control
        self.deps, self.app, self.client, self.headers, *_ = setup
        self.deps.config.feature_attention = True
        self.deps.config.feature_hitl = True
        self.deps.config.feature_observations = True
        dispatch = importlib.import_module('test_embedded_dispatch')
        _, self.binding, _ = dispatch.connect_local(setup)
        self.bindings = [self.binding]
        self.sessions, self.turns, self.records = [], [], []
        env = {key: value for key, value in os.environ.items()
            if key.upper() in {'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT'}}
        env.update(PATH='', HOME=str(control.parent / 'peer-home'), USERPROFILE=str(control.parent / 'peer-home'),
            PYTHONDONTWRITEBYTECODE='1')
        self.peers, self.wire = protocol.install_native((setup, self.binding, None), source,
            environment=env)

    def call(self, method, path, body=None, *, actor='operator', expected=None):
        response = self.client.request(method, path, json=body, headers=self.headers[actor])
        self.records.append({'method': method, 'path': path.split('?')[0], 'status': response.status_code})
        if expected is None:
            assert response.status_code < 400, (response.status_code, response.text)
        else:
            assert response.status_code in expected, (response.status_code, response.text)
        value = response.json()
        return value.get('data', value)

    def second_binding(self):
        """Approve another endpoint/profile; all grants precede session openings."""
        from test_binding_operator import prepare_operator

        from okto_nexus.domain.base import iso_plus
        first = self.binding
        proposal, apply = prepare_operator(self.client, self.headers, {
            'client_intent_id': 'backend-second-binding', 'agent_id_hint': first['agent_id'],
            'executor_id': first['executor_id'], 'adapter_id': 'codex_app_server',
            'candidate_ref': first['candidate_ref'], 'inventory_revision': first['inventory_revision'],
            'realization_ref': first['realization_ref'], 'workspace_id': first['workspace_id'],
            'alias': 'backend-second-profile'})
        assert proposal['can_apply'], proposal
        apply['client_intent_id'] = 'backend-second-apply'
        second = self.call('POST', '/v1/connections/bindings:apply', apply)
        assert second['binding_id'] != first['binding_id']
        assert second['agent_id'] == first['agent_id'] and second['workspace_id'] == first['workspace_id']
        self.call('POST', '/api/v1/harness/grants', {
            'actor_agent_id': second['agent_id'], 'endpoint_id': second['endpoint_id'],
            'actions': ['open', 'send', 'steer', 'interrupt', 'close'], 'max_executions': 10,
            'expires_at': iso_plus(self.deps.clock.now_iso(), 600)})
        self.bindings.append(second)
        return second

    def admit(self, binding, intent, *, actor='operator', **extra):
        managed = actor == 'operator'
        prefix = '/api/v1/runtime-management/runtime' if managed else '/v1/runtime'
        body = {'client_intent_id': 'backend-' + str(len(self.records)), 'intent': intent,
            'binding_id': binding['binding_id'], 'workspace_binding_id': binding['workspace_binding_id'], **extra}
        if managed:
            body['agent_id'] = binding['agent_id']
        resolution = self.call('POST', prefix + '/intents:resolve', body, actor=actor)
        assert resolution['can_submit'], resolution
        self.call('POST', prefix + '/operations', {key: resolution[key] for key in
            ('client_intent_id', 'operation_id', 'resolution_revision', 'intent_hash')}, actor=actor,
            expected=(200, 202))
        return resolution

    def receipt(self, operation):
        return self.call('GET', '/api/v1/runtime-management/runtime/operations/' + operation['operation_id'])

    def stage(self, operation, stages=('SUBMITTED', 'SUCCEEDED')):
        return wait(lambda: (value if (value := self.receipt(operation)).get('executor_stage') in stages else None),
            'Canonical receipt missing')

    def open(self, binding=None):
        binding = binding or self.binding
        opened = self.admit(binding, 'runtime.start', new_session=True)
        self.sessions.append((binding, opened['scope']['session_id']))
        self.stage(opened)
        wait(lambda: self.call('GET', '/api/v1/runtime-management/runtime/sessions/' + opened['scope']['session_id']
            + '?executor_id=' + binding['executor_id'])['lifecycle_state'] == 'READY', 'Canonical opening not READY')
        return opened['scope']['session_id']

    def turn(self, session, *, binding=None, question=False, blocking=True, actor='operator', queued=False):
        binding = binding or self.binding
        gate = 'release-' + str(len(self.turns))
        turn = self.admit(binding, 'turn.submit', actor=actor, session_id=session,
            text='HST:' + json.dumps({'gate': gate, 'question': question, 'blocking': blocking,
                'message': 'Backend functional fixture output'}))
        self.turns.append((binding, turn, gate))
        if not queued:
            self.stage(turn, ('SUBMITTED',))
            self.started(turn)
        if question:
            def canonical_question():
                value = self.call('GET', '/api/v1/runtime-management/runtime/input-requests')
                rows = value if isinstance(value, list) else value.get('items', [])
                with self.deps.connection_factory.unit_of_work(write=False) as uow:
                    row = uow.connection.execute("SELECT canonical_request_id FROM execution_native_requests "
                        "WHERE source_operation_id=? AND state='PENDING'", (turn['operation_id'],)).fetchone()
                return bool(rows) and row is not None
            wait(canonical_question, 'Canonical operator question missing')
        return turn

    def started(self, turn):
        def committed():
            with self.deps.connection_factory.unit_of_work(write=False) as uow:
                row = uow.connection.execute(
                    "SELECT e.payload_json FROM execution_event_ingress e JOIN execution_event_watermarks w "
                    "USING(server_id,executor_id,session_id,stream_epoch) WHERE e.server_id=? AND e.executor_id=? "
                    "AND e.session_id=? AND e.sequence<=w.committed_contiguous AND w.gap_state='none' "
                    "AND json_extract(e.payload_json,'$.operation_id')=? "
                    "AND json_extract(e.payload_json,'$.payload.delivery_phase')='started' ORDER BY e.sequence DESC LIMIT 1",
                    (turn['scope']['server_id'], turn['scope']['executor_id'], turn['scope']['session_id'], turn['operation_id'])).fetchone()
            return json.loads(row[0]) if row else None
        return wait(committed, 'Real Core started event not committed')

    def board(self, **filters):
        from urllib.parse import urlencode
        query = {'workspace_id': self.binding['workspace_id'], 'presentation_version': 2,
            'limit': 100, 'preview': 3, **filters}
        return self.call('GET', '/api/v1/home/harness-board?' + urlencode(query))

    @staticmethod
    def cards(board):
        return {item['connection']['binding_id']: (column, item)
            for column, page in board['columns'].items() for item in page['items'] if item['kind'] == 'harness'}

    @staticmethod
    def requests(board):
        result = []
        for page in board['columns'].values():
            for item in page['items']:
                if item['kind'] == 'request':
                    result.append(item)
                elif item['kind'] == 'harness':
                    result.extend(item.get('requests_preview', []))
        return result

    def snapshot(self):
        with self.deps.connection_factory.unit_of_work(write=False) as uow:
            return {table: [tuple(row) for row in uow.connection.execute('SELECT * FROM ' + table + ' ORDER BY rowid')]
                for table in ('runtime_execution_grants', 'execution_operations', 'execution_client_intents',
                    'execution_decisions', 'runtime_handoff_bindings', 'message_deliveries')}

    @contextmanager
    def hold_dispatch(self):
        lock = self.app.state.embedded_dispatch_owner.pump.send_lock
        self.client.portal.call(lock.acquire)
        try:
            yield
        finally:
            async def release():
                lock.release()
            self.client.portal.call(release)

    def close(self):
        """Terminal each own turn before closing; no forged future event/ACK."""
        failures = []
        for binding, turn, gate in self.turns:
            try:
                if self.receipt(turn).get('executor_stage') not in ('SUCCEEDED', 'FAILED', 'CANCELLED'):
                    native = self.started(turn)['payload']['turn_id']
                    interrupted = self.admit(binding, 'turn.interrupt', session_id=turn['scope']['session_id'],
                        target={'kind': 'native_turn_id', 'expected_turn_id': native})
                    self.stage(interrupted)
                    self.stage(turn, ('SUCCEEDED', 'FAILED', 'CANCELLED'))
            except BaseException as error:  # noqa: BLE001 -- finish all owned cleanup and fail below.
                failures.append(type(error).__name__)
            finally:
                (self.control / gate).touch()
        for binding, session in reversed(self.sessions):
            try:
                self.stage(self.admit(binding, 'runtime.close', session_id=session), ('SUCCEEDED',))
            except BaseException as error:  # noqa: BLE001 -- finish all owned cleanup and fail below.
                failures.append(type(error).__name__)
        if failures:
            # Physical containment of own inert peers is not a successful
            # canonical close. Preserve the failure before leaving lifespan.
            for peer in self.peers:
                peer.close()
        (self.control / 'cleanup.json').write_text(json.dumps({'canonical_failures': failures,
            'limits': 'No native application/resume acknowledgement inferred.'}) + '\n')
        assert not failures, ('Canonical owner cleanup failed', failures)


@contextmanager
def canonical_case(tmp_path, monkeypatch):
    root = Path(tempfile.mkdtemp(prefix='nexus-hst-backend-case-', dir=tmp_path))
    control = root / 'control'
    control.mkdir()
    local = importlib.import_module('test_local_realization')
    protocol = importlib.import_module('backend_batch_protocol')
    peer = importlib.import_module('backend_batch_peer_source')
    generator = local.local_setup.__wrapped__(root / 'setup', monkeypatch, SimpleNamespace(param='codex_app_server'))
    (root / 'setup').mkdir()
    setup = next(generator)
    owner = None
    try:
        owner = Owner(setup, monkeypatch, control, protocol, peer.source(protocol.BASE_SOURCE, control))
        yield owner
    finally:
        try:
            if owner is not None:
                owner.close()
        finally:
            generator.close()
