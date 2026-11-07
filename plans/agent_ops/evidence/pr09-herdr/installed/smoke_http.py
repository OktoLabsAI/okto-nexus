"""Installed helper -> real installed Nexus; only response loss is synthetic."""
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import sqlite3
import sys
import threading
import time

ROOT = Path(__file__).resolve().parent / 'qualified'
SITE = ROOT / 'venv/Lib/site-packages'
sys.path.append(sys.argv[1])  # shared dependency library, never the checkout
import httpx
import okto_nexus.observation_client as helper
from okto_nexus.observation_client import ObservationClient, ObservationClientError
assert Path(helper.__file__).resolve().is_relative_to(SITE)
metadata = json.loads((ROOT / 'server.json').read_text())
origin = metadata['url']
db_path = Path(metadata['home']) / 'nexus.db'
proof = {'revision': 1, 'url': origin, 'pid': metadata['pid'],
    'helper_module': str(Path(helper.__file__).resolve()), 'checks': [],
    'scope': 'Real installed Nexus HTTP and installed helper; synthetic registered external activity and loss relay; no provider or native execution'}


def check(condition, label):
    if not condition:
        raise AssertionError(label)
    proof['checks'].append(label)


def now():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')


def snapshot():
    with sqlite3.connect(db_path) as conn:
        conn.execute('BEGIN')
        names = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        result = {}
        for name in names:
            if name.startswith('observation_') or name == 'settings':
                continue
            query = 'SELECT * FROM "' + name.replace('"', '""') + '"'
            if name == 'events':
                query += " WHERE type NOT GLOB 'observation.*'"
            rows = sorted((tuple(row) for row in conn.execute(query)), key=repr)
            result[name] = {'rows': len(rows), 'sha256': hashlib.sha256(repr(rows).encode()).hexdigest()}
        return result


def refused(client, payload, expected):
    try:
        client.publish(payload)
    except ObservationClientError as exc:
        check(exc.status == expected and not exc.outcome_unknown, f'Helper classifies {expected} as known refusal')
        return
    raise AssertionError('Expected canonical refusal')


with httpx.Client(base_url=origin, timeout=10, trust_env=False,
    headers={'Origin': origin, 'X-Nexus-UI': '1'}) as manager:
    def call(method, path, **kwargs):
        response = manager.request(method, path, **kwargs)
        check(response.status_code == 200, f'{method} {path}: canonical success')
        value = response.json()
        check(value.get('ok') is True, 'Canonical envelope')
        return value['data']

    try:
        settings = {item['key']: item['value'] for item in call('GET', '/api/v1/settings')['items']}
        check(settings['feature_observations'] is False, 'OBS defaults off')
        check(settings['feature_harness_integrations'] is False and settings['feature_memory'] is False
              and settings['metrics_mode'] == 'disabled' and settings['embedding_mode'] == 'off',
              'Native execution, memory, metrics and embedding disabled')
        call('POST', '/api/v1/agents', json={'agent_id': 'pr09-observed-fixture'})
        call('PATCH', '/api/v1/agents/pr09-observed-fixture', json={
            'permissions': {'observations': {'manage_self': True, 'publish': True}}})
        before = snapshot()
        proof['canonical_before'] = before
        call('PATCH', '/api/v1/settings', json={'feature_observations': True})
        source = call('POST', '/api/v1/observations/sources', json={
            'agent_id': 'pr09-observed-fixture', 'source_kind': 'custom',
            'workspace_ids': ['pr09-smoke-workspace'], 'registration_ref': 'pr09-installed-explicit-fixture'})['source']
        source_path = '/api/v1/observations/sources/' + source['source_id']

        def instance_and_token(reference):
            instance = call('POST', source_path + '/instances', json={
                'expected_revision': source['revision'], 'workspace_id': 'pr09-smoke-workspace',
                'external_instance_ref': reference})['instance']
            issued = call('POST', source_path + '/tokens', json={
                'expected_revision': source['revision'], 'instance_grants': [{
                    'observed_instance_id': instance['observed_instance_id'], 'generation': instance['generation']}]})
            return instance, issued

        instance, issued = instance_and_token('pr09-helper-fixture')
        client = ObservationClient(origin, token=issued['token'])
        payload = {'schema_version': 1, 'source_id': source['source_id'],
            'observed_instance_id': instance['observed_instance_id'], 'generation': instance['generation'],
            'sequence': 1, 'state': 'working', 'evidence': 'reported', 'observed_at': now(),
            'valid_for_seconds': 2, 'reason_code': 'external_activity'}
        first = client.publish(payload)['receipts'][0]
        check(first['replayed'] is False, 'Installed helper validates first real receipt')
        check(client.publish(payload)['receipts'][0] == dict(first, replayed=True),
              'Exact replay preserves receipt and validity')
        refused(client, dict(payload, state='blocked'), 409)
        payload2 = dict(payload, sequence=2, observed_at=now(), state='blocked', reason_code='external_input_required')

        class LossRelay(BaseHTTPRequestHandler):
            calls = 0
            receipt = None
            def log_message(self, *args):
                pass
            def do_POST(self):
                type(self).calls += 1
                if self.path != '/v1/observations/activity':
                    self.send_error(404)
                    return
                body = self.rfile.read(int(self.headers['Content-Length']))
                with httpx.Client(timeout=10, trust_env=False) as forward:
                    response = forward.post(origin + self.path, content=body,
                        headers={'Authorization': self.headers['Authorization'], 'Content-Type': 'application/json'})
                if response.status_code == 200:
                    type(self).receipt = response.json()['data']['receipts'][0]
                self.connection.shutdown(socket.SHUT_RDWR)
                self.connection.close()

        relay = ThreadingHTTPServer(('127.0.0.1', 0), LossRelay)
        thread = threading.Thread(target=relay.serve_forever, daemon=True)
        thread.start()
        try:
            uncertain = ObservationClient(f'http://127.0.0.1:{relay.server_port}', token=issued['token'])
            try:
                uncertain.publish(payload2)
            except ObservationClientError as exc:
                check(exc.outcome_unknown, 'Lost real committed response remains outcome_unknown')
            else:
                raise AssertionError('Response loss was not classified')
            check(LossRelay.calls == 1 and LossRelay.receipt is not None, 'One publication only; no automatic retry')
            second = client.publish(payload2)['receipts'][0]
            check(second == dict(LossRelay.receipt, replayed=True), 'Caller exact retry recovers the real committed receipt')
        finally:
            relay.shutdown()
            relay.server_close()
            thread.join(3)
        expiry = datetime.fromisoformat(second['valid_until'].replace('Z', '+00:00'))
        time.sleep(max(0, (expiry - datetime.now(timezone.utc)).total_seconds()) + .1)
        check(client.publish(payload2)['receipts'][0] == second, 'Expired evidence replay neither renews nor changes receipt')
        call('POST', source_path + '/tokens/' + issued['credential']['token_id'] + '/revoke')
        refused(client, dict(payload2, sequence=3, observed_at=now()), 403)
        current = call('GET', '/api/v1/observations')['items'][0]
        check(current['activity_state'] == 'unknown' and current['observational_only'],
              'Revocation leaves observational history without current activity')
        runtime_instance, runtime_token = instance_and_token('pr09-explicit-herdr-qualification')
        credential_path = ROOT / 'qualification-credential.json'
        fd = os.open(credential_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as output:
            json.dump({'token': runtime_token['token'], 'server_origin': origin, 'source_id': source['source_id'],
                'source_revision': source['revision'], 'workspace_id': 'pr09-smoke-workspace',
                'observed_instance_id': runtime_instance['observed_instance_id'],
                'generation': runtime_instance['generation'], 'credential': runtime_token['credential']}, output)
        after = snapshot()
        proof['canonical_after'] = after
        check(before == after, 'All canonical tables unchanged by OBS/helper; only OBS records/events and explicit settings excluded')
        proof.update(result='passed', feature_at_handoff=True, credential_file=str(credential_path),
            credential_policy='Temporary qualification only; excluded from evidence collectors; never log contents',
            receipts=[first, second], service=call('GET', '/api/v1/service'))
    except Exception as exc:
        proof.update(result='failed', error_type=type(exc).__name__)
        raise
    finally:
        (ROOT / 'real-http-smoke.json').write_text(json.dumps(proof, indent=2), encoding='utf-8')
print(json.dumps({key: proof[key] for key in ('result', 'url', 'pid', 'feature_at_handoff', 'credential_file')}))
