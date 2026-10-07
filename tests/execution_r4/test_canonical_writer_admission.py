"""Independent database writers cannot invent a live runtime inventory."""
import json
from pathlib import Path
import subprocess
import sys

from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, wait_receipt
from test_canonical_delivery import connected_local, enable, send
from test_canonical_result_publication import current_turn


def test_independent_writer_cannot_invent_live_inventory(connected_local, monkeypatch):
    setup, binding, native = connected_local
    deps, _, _, headers, *_, root = setup
    enable(setup, binding)
    worker = Path(__file__).parents[1] / 'runtime_writer_process.py'
    response = subprocess.run([sys.executable, '-I', str(worker.resolve())],
        input=json.dumps(dict(home=str(deps.config.home_dir), root=str(root), enabled=True,
            key=headers['operator']['Authorization'].removeprefix('Bearer '),
            actor='operator', target='subject')),
        cwd=root, capture_output=True, text=True, encoding='utf-8', timeout=30)
    assert response.returncode == 0, response.stderr
    result = json.loads(response.stdout)
    assert not result['ok'] and result['error']['details']['blockers'] == ['inventory_not_fresh'], result
    with deps.connection_factory.unit_of_work(write=False) as uow:
        for table in ('messages', 'message_deliveries', 'delivery_outbox', 'execution_operations'):
            assert uow.connection.execute('SELECT COUNT(*) FROM '+table).fetchone()[0] == 0
    assert native.opens == 0
    # The owning HTTP composition has observed fresh inventory and can admit
    # the same logical request. A second database writer cannot invent it.
    result = send(setup, monkeypatch)
    assert result['ok'] and len(result['data']['runtime_operations']) == 1, result
    wait_receipt(setup, current_turn(setup))
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT consumer_kind FROM message_deliveries').fetchone()[0] == 'push'
        assert uow.connection.execute('SELECT COUNT(*) FROM delivery_outbox').fetchone()[0] == 1
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_domain_deliveries').fetchone()[0] == 2
    assert native.opens == 1 and len(native.native.sent) == 1
