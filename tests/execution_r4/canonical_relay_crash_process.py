"""Real owned Codex peers and a disposable application-process relay crash."""
import asyncio
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace

sys.path.insert(0, sys.argv[1])
tests = Path(sys.argv[2])
sys.path[:0] = [str(tests), str(tests / 'execution_r4')]
root, mode, cut, offset = Path(sys.argv[3]), sys.argv[4], sys.argv[5], int(sys.argv[6])
import pytest
from nexus_connector_core import InstallationCandidate
from nexus_connector_core.journal import SQLiteJournal
from nexus_connector_core.native.adapters.codex import CodexAppServerConnector
from nexus_connector_core.native.runtime_bridge import CopiedAdapterSession
from nexus_connector_core.native.redaction import NativeSecretRedactor
from test_harness_codex_connector import _FAKE_SERVER_SOURCE
from okto_nexus.bootstrap import embedded_inventory, dependencies, runtime_host
from okto_nexus.domain.base import iso_plus, utc_now_iso

patches = pytest.MonkeyPatch()
record_path = root / 'relay-record.json'
peers = []
source = _FAKE_SERVER_SOURCE.replace('def handle_turn(thread_id, turn_id, text, req_id):\n',
    'def handle_turn(thread_id, turn_id, text, req_id):\n'
    '    envelope = json.loads(text.split("\\n", 1)[1])\n'
    '    log({"fixture_operation":envelope["operation_id"], "recipient":envelope["recipient_agent_id"]})\n'
    + ('    if envelope["recipient_agent_id"] == "caller": text += " TRIGGER_HOLD"\n'
       if cut == 'accepted_child' else ''))

class Factory:
    async def open(self, prepared, session_id, context, *, stream_epoch):
        wire = root / ('native-' + str(os.getpid()) + '-' + context.agent_id + '.jsonl')
        peer = CodexAppServerConnector(command=[sys._base_executable, '-u', '-c', source, str(wire)],
            cwd=str(root / 'workspace'), env={})
        peers.append(peer)
        native = await asyncio.to_thread(peer.start, owning_agent_id=context.agent_id)
        return CopiedAdapterSession(peer, native, session_id=session_id, stream_epoch=stream_epoch,
            context=context, redactor=NativeSecretRedactor(()))

original_bootstrap = dependencies.bootstrap
def bootstrap(*args, **kwargs):
    deps = original_bootstrap(*args, **kwargs)
    deps.config.max_relay_depth = 1
    deps.config.feature_harness_integrations = True
    deps.clock.now_iso = lambda: iso_plus(utc_now_iso(), offset)
    return deps
patches.setattr(dependencies, 'bootstrap', bootstrap)
original_runtime = runtime_host.create_runtime
def create_runtime(*args, **kwargs):
    kwargs['native_factory'] = Factory()
    return original_runtime(*args, **kwargs)
patches.setattr(runtime_host, 'create_runtime', create_runtime)

if mode == 'produce':
    from test_local_realization import local_setup
    from test_canonical_delivery import connected_local
    from test_embedded_dispatch import connect_local, admit, wait_receipt
    from test_agent_recovery_isolation import create_agent
    from test_canonical_relay import send
    lifetime = local_setup.__wrapped__(root, patches, None)
    setup = next(lifetime)
    _, first, _ = connected_local.__wrapped__(setup)
    caller_setup = create_agent(setup, 'caller')
    setup[3]['caller'] = caller_setup[3]['subject']
    _, second, _ = connect_local(caller_setup, agent_id='caller')
    deps, app, client, headers, body, candidate, workspace = setup
    app.state.embedded_dispatch_owner.native_factory = Factory()
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agent_endpoints SET consumption='exclusive',response_policy='conversation',public_config=?",
            (json.dumps(dict(relay_results=True)),))
        uow.connection.execute("UPDATE runtime_policy_defaults SET session_policy='shared'")
        uow.connection.execute('UPDATE runtime_execution_grants SET expires_at=?', (iso_plus(deps.clock.now_iso(), 3600),))
    opened = admit(setup, first, 'relay-root-open', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    other = admit(caller_setup, second, 'relay-child-open', 'runtime.start', new_session=True)
    wait_receipt(caller_setup, other)
    from dataclasses import asdict
    temporary_record = record_path.with_suffix('.tmp')
    temporary_record.write_text(json.dumps(dict(home=str(deps.config.home_dir), headers=headers,
        native_pids=[peer._transport._proc.pid for peer in peers], candidate=asdict(candidate))), encoding='utf-8')
    temporary_record.replace(record_path)

    def crash():
        with deps.connection_factory.unit_of_work(write=False) as uow:
            marker = dict(root=dict(uow.connection.execute('SELECT * FROM runtime_causal_roots').fetchone()),
                operations=[dict(row) for row in uow.connection.execute('SELECT * FROM delivery_outbox ORDER BY created_at,operation_id')])
        (root / 'relay-cut.json').write_text(json.dumps(marker), encoding='utf-8')
        os._exit(79)

    original_event = SQLiteJournal.record_event
    async def record_event(journal, event):
        saved = await original_event(journal, event)
        if cut == 'journal_terminal' and event.payload.get('delivery_phase') == 'terminal':
            crash()
        return saved
    patches.setattr(SQLiteJournal, 'record_event', record_event)
    from okto_nexus.bootstrap import embedded_events
    project = embedded_events.commit_execution_events
    def project_events(*args, **kwargs):
        if cut == 'journal_terminal':
            raise OSError('Hold projection until owner death after Core capture')
        return project(*args, **kwargs)
    patches.setattr(embedded_events, 'commit_execution_events', project_events)
    from okto_nexus.application import execution_dispatch_pump
    reserve = execution_dispatch_pump.reserve_execution_dispatch
    def reserve_at_cut(*args, **kwargs):
        reservation = reserve(*args, **kwargs)
        if cut == 'committed_child' and reservation is not None:
            with deps.connection_factory.unit_of_work(write=False) as uow:
                row = uow.connection.execute('SELECT subject_agent_id,action FROM execution_operations WHERE operation_id=?',
                    (reservation.operation_id,)).fetchone()
            if row and tuple(row) == ('caller', 'turn.submit'):
                crash()
        return reservation
    patches.setattr(execution_dispatch_pump, 'reserve_execution_dispatch', reserve_at_cut)
    original_receipt = SQLiteJournal.record_receipt
    async def record_receipt(journal, key, receipt):
        saved = await original_receipt(journal, key, receipt)
        if cut == 'accepted_child' and receipt.stage == 'SUBMITTED':
            with deps.connection_factory.unit_of_work(write=False) as uow:
                row = uow.connection.execute("SELECT subject_agent_id,action FROM execution_operations WHERE operation_id=?",
                    (key.operation_id,)).fetchone()
            if row and tuple(row) == ('caller', 'turn.submit'):
                crash()
        return saved
    patches.setattr(SQLiteJournal, 'record_receipt', record_receipt)
    deadline = time.monotonic() + 30
    while not (root / 'relay-send').exists():
        assert time.monotonic() < deadline
        time.sleep(.02)
    result = send(setup, patches)
    assert result['ok'], result
    time.sleep(30)
    raise AssertionError('The requested relay crash cut was not reached')

record = json.loads(record_path.read_text(encoding='utf-8'))
candidate = InstallationCandidate(**record['candidate'])
patches.setattr(embedded_inventory, 'discover_local_candidates', lambda **_: SimpleNamespace(candidates=(candidate,)))
# The fixture models only the external credential vault, never a developer store.
from okto_nexus.bootstrap.embedded_tools import SessionToolVault
patches.setattr(SessionToolVault, 'store', lambda *args: None)
patches.setattr(SessionToolVault, 'remove', lambda *args: None)
from okto_nexus.adapters.inbound.cli.serve import run_serve
raise SystemExit(run_serve(sys.argv[7:]))
