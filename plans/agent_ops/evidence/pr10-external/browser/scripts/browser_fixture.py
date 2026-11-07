"""Explicit synthetic reports via the real HTTP API; private bearers stay local."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

sys.path.append('C:/Users/jpamb/AppData/Roaming/Python/Python313/site-packages')
import httpx

ROOT = Path(__file__).resolve().parent / 'qualified'
metadata = json.loads((ROOT / 'server.json').read_text(encoding='utf-8'))
origin = metadata['url']
private = ROOT / 'browser-fixture-private.json'
public = ROOT / 'browser-fixture-metadata.json'


def snapshot():
    with sqlite3.connect(Path(metadata['home']) / 'nexus.db') as conn:
        conn.execute('BEGIN')
        names = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        result = {}
        for name in names:
            if name.startswith('observation_') or name in ('settings', 'attention_preferences'):
                continue
            query = 'SELECT * FROM "' + name.replace('"', '""') + '"'
            if name == 'events':
                query += " WHERE type NOT GLOB 'observation.*'"
            rows = sorted((tuple(row) for row in conn.execute(query)), key=repr)
            result[name] = dict(rows=len(rows), sha256=hashlib.sha256(repr(rows).encode()).hexdigest())
        return result


with httpx.Client(base_url=origin, timeout=15, trust_env=False,
                  headers={'Origin': origin, 'X-Nexus-UI': '1'}) as manager:
    def call(method, path, **kwargs):
        response = manager.request(method, path, **kwargs)
        if response.status_code != 200:
            raise RuntimeError(f'{method} {path}: status {response.status_code}')
        value = response.json()
        assert value['ok'] is True
        return value['data']

    def save():
        private.write_text(json.dumps(registry, indent=2), encoding='utf-8')
        public.write_text(json.dumps({label: {key: value for key, value in item.items() if key != 'token'}
            for label, item in registry.items()}, indent=2), encoding='utf-8')

    def publish(label, state, *, ttl=3600, completion=None, reason=None):
        item = registry[label]
        item['sequence'] += 1
        save()  # Reserve a monotonic sequence before HTTP; never retry implicitly.
        payload = dict(schema_version=1, source_id=item['source_id'], observed_instance_id=item['observed_instance_id'],
            generation=item['generation'], sequence=item['sequence'], state=state, evidence='inferred',
            observed_at=datetime.now(timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z'),
            valid_for_seconds=ttl)
        if completion is not None:
            payload['current_completion_ref'] = completion
        if reason is not None:
            payload.update(reason_code='external_input_required', reason_text=reason)
        with httpx.Client(timeout=15, trust_env=False) as publisher:
            response = publisher.post(origin + '/v1/observations/activity', json=payload,
                headers={'Authorization': 'Bearer ' + item['token']})
        if response.status_code != 200:
            raise RuntimeError(f'Publish {label}: status {response.status_code}; no automatic retry')
        receipt = response.json()['data']['receipts'][0]
        item['last_receipt'] = receipt
        save()
        return receipt

    action = sys.argv[1]
    if action == 'initial':
        assert not private.exists()
        registry = {}
        call('PATCH', '/api/v1/settings', json=dict(feature_observations=True, feature_attention=True))
        for agent in ('pr10-observed-a', 'pr10-observed-b'):
            call('POST', '/api/v1/agents', json=dict(agent_id=agent))
            call('PATCH', '/api/v1/agents/' + agent, json=dict(
                permissions={'observations': {'manage_self': True, 'publish': True}}))
        sources = {}
        for suffix in ('a', 'b'):
            sources[suffix] = call('POST', '/api/v1/observations/sources', json=dict(
                agent_id='pr10-observed-' + suffix, source_kind='custom',
                workspace_ids=['pr10-workspace-' + suffix], registration_ref='pr10-browser-source-' + suffix))['source']
        for label, suffix in [('working', 'a'), ('blocked', 'a'), ('complete', 'a'), ('stale', 'a'), ('empty', 'a'), ('other', 'b')]:
            source = sources[suffix]
            path = '/api/v1/observations/sources/' + source['source_id']
            instance = call('POST', path + '/instances', json=dict(expected_revision=source['revision'],
                workspace_id='pr10-workspace-' + suffix,
                external_instance_ref='javascript:alert(1) · <unsafe> · bloqueado' if label == 'blocked' else 'pr10-' + label))['instance']
            issued = call('POST', path + '/tokens', json=dict(expected_revision=source['revision'],
                instance_grants=[dict(observed_instance_id=instance['observed_instance_id'], generation=instance['generation'])]))
            registry[label] = dict(source_id=source['source_id'], source_revision=source['revision'],
                observed_instance_id=instance['observed_instance_id'], generation=instance['generation'],
                agent_id='pr10-observed-' + suffix, workspace_id=instance['workspace_id'],
                sequence=0, token=issued['token'], token_id=issued['credential']['token_id'], expires_at=issued['credential']['expires_at'])
        save()
        (ROOT / 'browser-canonical-before.json').write_text(json.dumps(snapshot(), indent=2), encoding='utf-8')
        publish('working', 'working')
        publish('blocked', 'blocked', reason='<svg onload=window.PR10_XSS=1> waiting for input & review </svg>')
        publish('complete', 'idle', completion='pr10-completion-1')
        publish('complete', 'idle', completion='pr10-completion-1')
        publish('complete', 'idle', completion='pr10-completion-2')
        publish('stale', 'working', ttl=2)
        publish('other', 'working')
    else:
        registry = json.loads(private.read_text(encoding='utf-8'))
        if action == 'publish':
            publish(sys.argv[2], sys.argv[3], ttl=int(sys.argv[4]) if len(sys.argv) > 4 else 3600)
        elif action == 'renew':
            for item in registry.values():
                issued = call('POST', '/api/v1/observations/sources/' + item['source_id'] + '/tokens', json=dict(
                    expected_revision=item['source_revision'], instance_grants=[dict(
                        observed_instance_id=item['observed_instance_id'], generation=item['generation'])]))
                item.update(token=issued['token'], token_id=issued['credential']['token_id'], expires_at=issued['credential']['expires_at'])
            save()
        elif action == 'rotate':
            item = registry[sys.argv[2]]
            value = call('POST', '/api/v1/observations/sources/' + item['source_id'] + '/instances/'
                + item['observed_instance_id'] + '/rotate', json=dict(expected_revision=item['source_revision'],
                    expected_generation=item['generation']))['instance']
            item['generation'], item['sequence'] = value['generation'], 0
            save()
        elif action == 'toggle':
            call('PATCH', '/api/v1/settings', json=dict(feature_observations=sys.argv[2] == 'on'))
        elif action == 'proof':
            before = json.loads((ROOT / 'browser-canonical-before.json').read_text(encoding='utf-8'))
            after = snapshot()
            result = dict(tables=len(before), unchanged=before == after,
                changed=[key for key in sorted(set(before) | set(after)) if before.get(key) != after.get(key)],
                summary=call('GET', '/api/v1/observations/summary'),
                attention=call('GET', '/api/v1/attention', params={'state': 'all', 'limit': 200}))
            (ROOT / 'browser-server-proof.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
            assert result['unchanged'], result['changed']
        else:
            raise ValueError('Unknown qualification action')
print(json.dumps(dict(action=action, public_metadata=str(public), private_bearers_excluded=True)))
