"""Real HTTP OBS smoke; credentials stay in memory and never enter reports."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import time

import httpx

ROOT = Path(__file__).resolve().parent / 'qualified'
metadata = json.loads((ROOT / 'server.json').read_text())
db_path = Path(metadata['home']) / 'nexus.db'
assert db_path.is_file()
proof = {'revision': 1, 'url': metadata['url'], 'pid': metadata['pid'],
         'clients': 'synthetic local fixture; no real provider/client participation', 'checks': []}


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


with httpx.Client(base_url=metadata['url'], timeout=10,
                  headers={'Origin': metadata['url'], 'X-Nexus-UI': '1'}) as client:
    def call(method, path, expected=200, **kwargs):
        response = client.request(method, path, **kwargs)
        check(response.status_code == expected, f'{method} {path} -> {expected}')
        value = response.json()
        if expected == 200:
            check(value.get('ok') is True, f'{method} {path}: canonical success envelope')
            return value['data']
        return value

    try:
        settings = call('GET', '/api/v1/settings')['items']
        obs_flag = next(item for item in settings if item['key'] == 'feature_observations')
        check(obs_flag['value'] is False and obs_flag['editable'], 'OBS defaults off and is not pinned')
        check(next(item for item in settings if item['key'] == 'feature_harness_integrations')['value'] is False,
              'Runtime integration remains disabled')
        created = call('POST', '/api/v1/agents', json={'agent_id': 'pr08-observed-fixture'})
        agent_key = created['api_key']
        call('PATCH', '/api/v1/agents/pr08-observed-fixture', json={
            'permissions': {'observations': {'manage_self': True, 'publish': True}}})
        before = snapshot()
        proof['canonical_before'] = before
        registration = {'agent_id': 'pr08-observed-fixture', 'source_kind': 'custom',
                        'workspace_ids': ['pr08-smoke-workspace'], 'registration_ref': 'pr08-installed-consent'}
        call('POST', '/api/v1/observations/sources', expected=409, json=registration)
        call('PATCH', '/api/v1/settings', json={'feature_observations': True})
        source = call('POST', '/api/v1/observations/sources', json=registration)['source']
        source_path = '/api/v1/observations/sources/' + source['source_id']
        instance = call('POST', source_path + '/instances', json={
            'expected_revision': source['revision'], 'workspace_id': 'pr08-smoke-workspace',
            'external_instance_ref': 'pr08-synthetic-occupant'})['instance']
        issued = call('POST', source_path + '/tokens', json={
            'expected_revision': source['revision'], 'instance_grants': [{
                'observed_instance_id': instance['observed_instance_id'], 'generation': instance['generation']}]})
        publish_headers = {'Authorization': 'Bearer ' + issued['token']}
        payload = {'schema_version': 1, 'source_id': source['source_id'],
                   'observed_instance_id': instance['observed_instance_id'], 'generation': instance['generation'],
                   'sequence': 1, 'state': 'blocked', 'evidence': 'reported', 'observed_at': now(),
                   'valid_for_seconds': 2, 'reason_code': 'external_input_required'}
        first = call('POST', '/v1/observations/activity', headers=publish_headers, json=payload)['receipts'][0]
        repeated = call('POST', '/v1/observations/activity', headers=publish_headers, json=payload)['receipts'][0]
        check(repeated == dict(first, replayed=True), 'Replay preserves exact receipt and validity')
        current = call('GET', '/api/v1/observations')['items'][0]
        check(current['freshness'] == 'current' and current['activity_state'] == 'blocked', 'Authorized read shows only reported external activity')
        check(current['canonical_session_ref'] is None and current['observational_only'], 'No canonical session or productive success inferred')
        call('POST', '/mcp/', expected=401, headers=publish_headers, json={})
        call('POST', '/api/v1/agents/pr08-observed-fixture/regenerate-key', expected=401, headers=publish_headers)
        call('GET', '/api/v1/observations', expected=401, headers=publish_headers)
        call('POST', '/v1/observations/activity', expected=401,
             headers={'Authorization': 'Bearer ' + agent_key}, json=payload)
        call('PATCH', '/api/v1/settings', json={'feature_observations': False})
        call('POST', '/v1/observations/activity', expected=409, headers=publish_headers, json=payload)
        historical = call('GET', '/api/v1/observations')['items'][0]
        check(historical['freshness'] == 'unavailable' and historical['activity_state'] == 'unknown', 'Feature off retains authorized history without current activity')
        check(historical['last_report'] == current['last_report'], 'Disabling ingestion preserves historical receipt')
        expiry = datetime.fromisoformat(first['valid_until'].replace('Z', '+00:00'))
        time.sleep(max(0, (expiry - datetime.now(timezone.utc)).total_seconds()) + .15)
        call('PATCH', '/api/v1/settings', json={'feature_observations': True})
        resumed = call('GET', '/api/v1/observations')['items'][0]
        check(resumed['freshness'] == 'stale' and resumed['activity_state'] == 'unknown', 'Re-enable does not renew expired evidence or infer idle/completion')
        check(resumed['last_report'] == current['last_report'], 'Re-enable preserves original receipt unchanged')
        call('PATCH', '/api/v1/settings', json={'feature_observations': False})
        after = snapshot()
        proof['canonical_after'] = after
        proof['canonical_changed_tables'] = [name for name in before.keys() | after.keys() if before.get(name) != after.get(name)]
        check(before == after, 'All canonical tables unchanged; only OBS tables/events and explicit settings writes excluded')
        with sqlite3.connect(db_path) as conn:
            events = conn.execute("SELECT type,count(*) FROM events WHERE type GLOB 'observation.*' GROUP BY type").fetchall()
        check(events == [('observation.activity', 1)], 'One observational event for initial report; replay and toggles emit none')
        proof['result'] = 'passed'
        proof['feature_at_handoff'] = False
        proof['service'] = call('GET', '/api/v1/service')
    except Exception as exc:
        proof['result'] = 'failed'
        proof['error_type'] = type(exc).__name__
        proof['error'] = str(exc)
        raise
    finally:
        (ROOT / 'real-http-smoke.json').write_text(json.dumps(proof, indent=2), encoding='utf-8')
print(json.dumps({key: proof[key] for key in ('result', 'url', 'pid', 'feature_at_handoff', 'canonical_changed_tables')}, indent=2))
