"""Explicit operator provisioning for this one isolated qualification Server.

provision OUTPUT; renew OLD OUTPUT; rotate OLD OUTPUT. No automatic recovery.
Credential files are temporary, never evidence, and never overwritten or printed.
"""
import json
import os
from pathlib import Path
import sys
import httpx

ROOT = Path(__file__).resolve().parent / 'qualified'


def output_path(value):
    path = Path(value).resolve()
    if path.parent != ROOT or path.exists():
        raise RuntimeError('A new qualification-only output file is required')
    return path


def publish_file(path, source, instance, issued, origin):
    value = {'token': issued['token'], 'server_origin': origin, 'source_id': source['source_id'],
        'source_kind': source['source_kind'], 'source_revision': source['revision'],
        'agent_id': source['agent_id'], 'workspace_id': instance['workspace_id'],
        'observed_instance_id': instance['observed_instance_id'], 'generation': instance['generation'],
        'credential': issued['credential']}
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as target:
        json.dump(value, target)
        target.flush()
        os.fsync(target.fileno())
    safe = {key: item for key, item in value.items() if key != 'token'}
    safe.update(credential_file=str(path), command='qualification_management.py',
        renew='renew OLD_CREDENTIAL_FILE NEW_CREDENTIAL_FILE: same generation, atomic replacement token',
        rotate='rotate OLD_CREDENTIAL_FILE NEW_CREDENTIAL_FILE: explicit generation change then replacement token')
    path.with_suffix('.metadata.json').write_text(json.dumps(safe, indent=2), encoding='utf-8')
    return safe


def manage(action, previous, destination):
    output = output_path(destination)
    server = json.loads((ROOT / 'server.json').read_text())
    owner = json.loads((ROOT / 'server-owner.json').read_text())
    origin = server['url']
    with httpx.Client(base_url=origin, timeout=10, trust_env=False,
        headers={'Origin': origin, 'X-Nexus-UI': '1'}) as client:
        def call(method, path, body=None):
            response = client.request(method, path, **({'json': body} if body is not None else {}))
            if response.status_code != 200:
                raise RuntimeError('Canonical management refused: HTTP ' + str(response.status_code))
            value = response.json()
            if value.get('ok') is not True:
                raise RuntimeError('Invalid canonical management envelope')
            return value['data']

        current = call('GET', '/api/v1/service')
        if (current['pid'], current['instance_id'], current['generation']) != (
                owner['server_pid'], owner['instance_id'], owner['generation']):
            raise RuntimeError('Isolated Server owner changed')
        if action == 'provision':
            source = call('POST', '/api/v1/observations/sources', {
                'agent_id': 'pr09-observed-fixture', 'source_kind': 'herdr',
                'workspace_ids': ['pr09-smoke-workspace'],
                'registration_ref': 'pr09-real-herdr-explicit-qualification'})['source']
            base = '/api/v1/observations/sources/' + source['source_id']
            instance = call('POST', base + '/instances', {'expected_revision': source['revision'],
                'workspace_id': 'pr09-smoke-workspace',
                'external_instance_ref': 'pr09-real-herdr-explicit-occupant'})['instance']
            old_token = None
        else:
            old_path = Path(previous).resolve()
            if old_path.parent != ROOT:
                raise RuntimeError('Qualification input must be local to this campaign')
            old = json.loads(old_path.read_text())
            base = '/api/v1/observations/sources/' + old['source_id']
            source = call('GET', base)['source']
            items = call('GET', base + '/instances')['items']
            instance = next(item for item in items if item['observed_instance_id'] == old['observed_instance_id'])
            if instance['generation'] != old['generation']:
                raise RuntimeError('Generation changed; explicit refreshed management review is required')
            if action == 'rotate':
                instance = call('POST', base + '/instances/' + instance['observed_instance_id'] + '/rotate',
                    {'expected_revision': source['revision'], 'expected_generation': instance['generation']})['instance']
            old_token = old['credential']['token_id']
        body = {'expected_revision': source['revision'], 'instance_grants': [{
            'observed_instance_id': instance['observed_instance_id'], 'generation': instance['generation']}]}
        if old_token is not None:
            body['replaces_token_id'] = old_token
        issued = call('POST', base + '/tokens', body)
        return publish_file(output, source, instance, issued, origin)


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == 'provision':
        result = manage('provision', None, sys.argv[2])
    elif len(sys.argv) == 4 and sys.argv[1] in ('renew', 'rotate'):
        result = manage(sys.argv[1], sys.argv[2], sys.argv[3])
    else:
        raise SystemExit('Expected provision OUTPUT, renew OLD OUTPUT, or rotate OLD OUTPUT')
    print(json.dumps(result, indent=2))
