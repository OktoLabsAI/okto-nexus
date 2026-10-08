"""Actual application death around Core capture and Server result commits."""
from contextlib import closing
from datetime import datetime, timezone
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
from test_runtime_relay_process_restart import PeerWitness


@pytest.mark.parametrize('cut', ['before_output_capture', 'before_terminal_capture',
                                'after_terminal_capture', 'after_terminal_capture_burst', 'after_projection_commit'])
def test_actual_owner_crash_recovers_only_durable_native_results(tmp_path, cut):
    helper = Path(__file__).with_name('canonical_crash_process.py')
    tests = Path(__file__).parents[1]
    package_root = str(Path(okto_nexus.__file__).resolve().parent.parent)
    env = {k: v for k, v in os.environ.items() if k.upper() in {'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP'}}
    env.update(PATH=str(Path(os.environ.get('SYSTEMROOT', 'C:/Windows')) / 'System32'),
        HOME=str(tmp_path), USERPROFILE=str(tmp_path), PYTHONIOENCODING='utf-8', OKTO_NEXUS_NO_BANNER='1')
    command = [sys.executable, '-I', str(helper), package_root, str(tests), str(tmp_path)]
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    producer_log = tmp_path / 'producer.log'
    witness = restarted = None
    def rows(sql, params=()):
        with closing(sqlite3.connect(tmp_path / 'home/nexus.db', timeout=10)) as db:
            db.row_factory = sqlite3.Row
            return [dict(row) for row in db.execute(sql, params)]
    with producer_log.open('w', encoding='utf-8') as output:
        producer = subprocess.Popen(command + ['produce', cut], env=env, cwd=tmp_path,
            stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT, creationflags=flags)
        try:
            record_path = tmp_path / 'crash-record.json'
            deadline = time.monotonic() + 30
            while not record_path.exists():
                assert producer.poll() is None, producer_log.read_text(encoding='utf-8')
                assert time.monotonic() < deadline, producer_log.read_text(encoding='utf-8')
                time.sleep(.02)
            record = json.loads(record_path.read_text(encoding='utf-8'))
            witness = PeerWitness(record['native_pid'])
            (tmp_path / 'allow-send').touch()
            assert producer.wait(timeout=30) == 78, producer_log.read_text(encoding='utf-8')
            witness.assert_stopped()
            marker = json.loads((tmp_path / 'crash-cut.json').read_text(encoding='utf-8'))
            assert marker['session_id'] == record['opened']['scope']['session_id']
            expiry = datetime.fromisoformat(record['owner_expiry'].replace('Z', '+00:00'))
            remaining = (expiry - datetime.now(timezone.utc)).total_seconds()
            assert remaining <= 45
            if remaining > 0:
                time.sleep(remaining + .1)
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                port = sock.getsockname()[1]
            restart_log = tmp_path / 'restart.log'
            with restart_log.open('w', encoding='utf-8') as restart_output:
                restarted = subprocess.Popen(command + ['serve', cut, '--home', record['home'],
                    '--host', '127.0.0.1', '--port', str(port), '--feature-harness-integrations', 'true',
                    '--embedding-mode', 'off', '--harness-root', str(tmp_path)], env=env, cwd=tmp_path,
                    stdin=subprocess.DEVNULL, stdout=restart_output, stderr=subprocess.STDOUT, creationflags=flags)
                durable = cut.startswith('after_terminal_capture') or cut == 'after_projection_commit'
                with httpx.Client(base_url=f'http://127.0.0.1:{port}', trust_env=False, timeout=5,
                                  headers=record['headers']['operator']) as client:
                    deadline = time.monotonic() + 35
                    while True:
                        assert restarted.poll() is None, restart_log.read_text(encoding='utf-8')
                        assert time.monotonic() < deadline, (rows('SELECT * FROM execution_agent_recovery'),
                            rows('SELECT status,reason FROM delivery_outbox'), restart_log.read_text(encoding='utf-8'))
                        try:
                            response = client.get('/api/v1/harness/outbox', params={'operation_id': marker['operation_id']})
                            results = rows('SELECT * FROM runtime_results WHERE canonical_operation_id=?', (marker['turn'],))
                            domain = rows('SELECT * FROM delivery_outbox WHERE operation_id=?', (marker['operation_id'],))[0]
                            recovered = rows("SELECT state FROM execution_agent_recovery WHERE agent_id='subject'")
                            if response.status_code == 200 and recovered and recovered[0]['state'] == 'READY':
                                if durable and results and results[0]['publication_state'] == 'PUBLISHED':
                                    break
                                if not durable and domain['status'] == 'OUTCOME_UNKNOWN':
                                    break
                        except httpx.TransportError:
                            pass
                        time.sleep(.05)
                    assert response.json()['ok'], response.text
                    receipts = rows("SELECT message_id FROM messages WHERE subject LIKE 'runtime processing receipt:%'")
                    delivery = rows('SELECT status,consumer_kind FROM message_deliveries WHERE delivery_id=?', (marker['delivery_id'],))[0]
                    if durable:
                        assert len(results) == len(receipts) == 1
                        assert 'Please review this message.' in results[0]['output_text']
                        assert results[0]['canonical_operation_id'] == marker['turn']
                        assert domain['canonical_terminal_operation_id'] == marker['turn']
                        assert delivery['status'] == 'read'
                        if cut.endswith('_burst'):
                            assert rows("SELECT count(*) AS n FROM execution_event_ingress WHERE event_type='text_delta'")[0]['n'] == 140
                    else:
                        assert not results and not receipts
                        assert domain['canonical_terminal_operation_id'] is None
                        assert delivery['status'] != 'read' and delivery['consumer_kind'] == 'push'
                    for _ in range(3):
                        inspected = client.get('/api/v1/harness/outbox', params={'operation_id': marker['operation_id']})
                        assert inspected.status_code == 200
                    wire = [json.loads(line) for line in Path(record['wire']).read_text(encoding='utf-8').splitlines()]
                    assert sum(item.get('method') == 'turn/start' for item in wire) == 1
                    assert not (tmp_path / 'unexpected-native-launch').exists()
                    assert rows('PRAGMA foreign_key_check') == []
                    shutdown = client.post('/v1/runtime/shutdown', json={'timeout_seconds': 2})
                    assert shutdown.status_code in {200, 202}, shutdown.text
                assert restarted.wait(timeout=15) == 0, restart_log.read_text(encoding='utf-8')
        finally:
            for process in (restarted, producer):
                if process is not None and process.poll() is None:
                    process.kill()
                    process.wait(timeout=10)
            if witness is not None:
                witness.close()
