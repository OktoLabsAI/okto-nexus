"""A fresh serve process resumes only a provably unsent relay child."""
from contextlib import closing
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import time

import httpx
import okto_nexus
import pytest
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'tests'), str(ROOT / 'tests/execution_r4')]
from test_runtime_relay_process_restart import PeerWitness

@pytest.mark.parametrize('cut,offset', [('journal_terminal', 600), ('journal_terminal', 1800),
    ('committed_child', 600), ('accepted_child', 600)])
def test_actual_owner_crash_preserves_relay_lineage(tmp_path, cut, offset):
    helper = Path(__file__).with_name('canonical_relay_crash_process.py')
    package = str(Path(okto_nexus.__file__).resolve().parent.parent)
    command = [sys.executable, '-I', str(helper), package, str(ROOT / 'tests'), str(tmp_path)]
    env = {k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','TEMP','TMP'}}
    env.update(PATH=str(Path(os.environ.get('SYSTEMROOT', 'C:/Windows')) / 'System32'),
        HOME=str(tmp_path), USERPROFILE=str(tmp_path), PYTHONIOENCODING='utf-8', OKTO_NEXUS_NO_BANNER='1')
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    processes, witnesses = [], []
    def rows(sql):
        with closing(sqlite3.connect(tmp_path / 'home/nexus.db', timeout=10)) as conn:
            conn.row_factory = sqlite3.Row
            return [dict(row) for row in conn.execute(sql)]
    def await_file(path, process, log):
        until = time.monotonic() + 40
        while not path.exists():
            assert process.poll() is None, log.read_text(encoding='utf-8')
            assert time.monotonic() < until, log.read_text(encoding='utf-8')
            time.sleep(.02)
    try:
        log = tmp_path / 'producer.log'
        with log.open('w', encoding='utf-8') as output:
            producer = subprocess.Popen(command + ['produce', cut, '0'], env=env, cwd=tmp_path,
                stdout=output, stderr=subprocess.STDOUT, creationflags=flags)
            processes.append(producer)
            await_file(tmp_path / 'relay-record.json', producer, log)
            record = json.loads((tmp_path / 'relay-record.json').read_text(encoding='utf-8'))
            witnesses = [PeerWitness(pid) for pid in record['native_pids']]
            assert len(witnesses) == 2
            (tmp_path / 'relay-send').touch()
            assert producer.wait(timeout=40) == 79, log.read_text(encoding='utf-8')
            for witness in witnesses:
                witness.assert_stopped()
        marker = json.loads((tmp_path / 'relay-cut.json').read_text(encoding='utf-8'))
        assert len(marker['operations']) == (1 if cut == 'journal_terminal' else 2)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        restart_log = tmp_path / 'restart.log'
        with restart_log.open('w', encoding='utf-8') as output:
            restarted = subprocess.Popen(command + ['serve', cut, str(offset), '--home', record['home'],
                '--host', '127.0.0.1', '--port', str(port), '--feature-harness-integrations', 'true',
                '--embedding-mode', 'off', '--harness-root', str(tmp_path)], env=env, cwd=tmp_path,
                stdout=output, stderr=subprocess.STDOUT, creationflags=flags)
            processes.append(restarted)
            with httpx.Client(base_url=f'http://127.0.0.1:{port}', timeout=5,
                    trust_env=False, headers=record['headers']['operator']) as client:
                until = time.monotonic() + 60
                while True:
                    assert restarted.poll() is None, restart_log.read_text(encoding='utf-8')
                    operations = rows('SELECT * FROM delivery_outbox ORDER BY created_at,operation_id')
                    results = rows('SELECT * FROM runtime_results ORDER BY captured_at,result_id')
                    recovered = rows('SELECT state FROM execution_agent_recovery')
                    expected = 1 if offset == 1800 else 2
                    finished = (len(results) == (1 if cut == 'accepted_child' else expected)
                        and all(r['publication_state'] == 'PUBLISHED' for r in results)
                        and all(r['state'] == 'READY' for r in recovered))
                    if finished and len(operations) == expected and (cut != 'accepted_child' or operations[-1]['status'] == 'OUTCOME_UNKNOWN'):
                        break
                    assert time.monotonic() < until, ([(o['status'],o['reason']) for o in operations],
                        [(r['publication_state'],r['relay_state'],r['relay_reason']) for r in results], recovered,
                        restart_log.read_text(encoding='utf-8'))
                    time.sleep(.05)
                assert operations[0]['canonical_terminal_operation_id'] is not None
                assert operations[0]['status'] == 'ACCEPTED'
                if cut == 'committed_child':
                    child = operations[-1]
                    inspected = client.get('/api/v1/harness/outbox', params={'operation_id': child['operation_id']})
                    assert inspected.status_code == 200, inspected.text
                    item = inspected.json()['data']['items'][0]
                    history = item['canonical_attempt_history']
                    assert len(history) == 1 and history[0]['attempt_number'] == 1
                    previous = history[0]['operation_id']
                    assert previous != child['attempt_id'] and child['attempt_count'] == 2
                    assert history[0]['proof_operation_id'] == previous
                    assert history[0]['proof_receipt_revision'] is None
                    proof, = item['unsent_dispatch_history']
                    assert proof['operation_id'] == previous and proof['attempt_no'] == 1
                    assert proof['previous_owner'] != proof['fenced_by_owner']
                    assert proof['previous_generation'] < proof['fenced_by_generation']
                    assert {entry['attempt_id'] for entry in item['attempt_history']} >= {previous, child['attempt_id']}
                    assert rows("SELECT * FROM execution_receipts WHERE operation_id='" + previous + "'") == []
                if cut == 'accepted_child':
                    assert operations[-1]['canonical_terminal_operation_id'] is None
                if offset == 1800:
                    assert results[0]['relay_state'] == 'BLOCKED' and results[0]['relay_reason'] == 'QUOTA_EXCEEDED'
                causal, = rows('SELECT * FROM runtime_causal_roots')
                assert causal['root_operation_id'] == marker['root']['root_operation_id']
                assert causal['deadline'] == marker['root']['deadline']
                assert (causal['generated_messages'], causal['admitted_executions']) == (expected - 1, expected)
                assert {o['root_operation_id'] for o in operations} == {causal['root_operation_id']}
                assert [json.loads(o['envelope'])['hop_count'] for o in operations] == list(range(expected))
                wire = [json.loads(line) for file in tmp_path.glob('native-*.jsonl')
                    for line in file.read_text(encoding='utf-8').splitlines()]
                writes = [item['fixture_operation'] for item in wire if 'fixture_operation' in item]
                assert sorted(writes) == sorted(o['operation_id'] for o in operations)
                assert rows('PRAGMA foreign_key_check') == []
                assert client.post('/v1/runtime/shutdown', json=dict(timeout_seconds=2)).status_code in (200,202)
            assert restarted.wait(timeout=20) == 0, restart_log.read_text(encoding='utf-8')
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)
        for witness in witnesses:
            witness.close()
