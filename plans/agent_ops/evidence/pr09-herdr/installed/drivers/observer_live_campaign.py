"""Actual installed observer CLI -> actual Herdr -> actual installed Nexus."""
import hashlib
import json
import os
from pathlib import Path
import runpy
import sqlite3
import subprocess
from urllib.request import ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parent
Q = ROOT / 'qualified'
SERVER = json.loads((Q / 'server.json').read_text())
SECRET = json.loads((Q / 'qualification-herdr-credential.json').read_text())
HERDR = runpy.run_path(r'C:\Users\jpamb\AppData\Local\Temp\pr09-herdr-live.py')
ENV = dict(HERDR['ENV'])
STATE = Q / 'observer-state.json'
records = []

def canonical_snapshot():
    with sqlite3.connect(Path(SERVER['home']) / 'nexus.db') as connection:
        connection.execute('BEGIN')
        tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        result = {}
        for name in tables:
            if name.startswith('observation_') or name == 'settings':
                continue
            query = 'SELECT * FROM "' + name.replace('"', '""') + '"'
            if name == 'events':
                query += " WHERE type NOT GLOB 'observation.*'"
            rows = sorted((tuple(row) for row in connection.execute(query)), key=repr)
            result[name] = dict(rows=len(rows), sha256=hashlib.sha256(repr(rows).encode()).hexdigest())
        return result

def cli(name, arguments, *, token=False, expected=0):
    environment = dict(ENV)
    if token:
        environment['NEXUS_PR09_OBSERVATION_TOKEN'] = SECRET['token']
    result = subprocess.run(['rtk', 'proxy', SERVER['python'], '-I', str(ROOT / 'observer_entry.py'),
        'observe', 'herdr', *arguments], cwd=Q, env=environment, capture_output=True,
        timeout=40, creationflags=subprocess.CREATE_NO_WINDOW)
    (Q / ('observer-' + name + '.stdout.txt')).write_bytes(result.stdout)
    (Q / ('observer-' + name + '.stderr.txt')).write_bytes(result.stderr)
    assert SECRET['token'].encode() not in result.stdout + result.stderr
    values = [json.loads(line) for line in result.stdout.decode('utf-8').splitlines()]
    records.append(dict(stage=name, exit_code=result.returncode, output=values))
    if result.returncode != expected:
        raise AssertionError('Unexpected CLI result for ' + name + ': ' + str(result.returncode))
    return values[-1]

def publish(name):
    return cli(name, ['run', '--state', str(STATE), '--token-env', 'NEXUS_PR09_OBSERVATION_TOKEN', '--once'], token=True)

def hook(state, seq):
    return HERDR['call']('installed-fixture-' + state + '-' + str(seq),
        ['pane', 'report-agent', 'w1:p1', '--source', 'nexus-pr09-fixture',
         '--agent', 'nexus-pr09-fixture', '--state', state, '--seq', str(seq)])

def observation_view():
    request = Request(SERVER['url'] + '/api/v1/observations', headers={'Origin': SERVER['url'], 'X-Nexus-UI': '1'})
    with build_opener(ProxyHandler({})).open(request, timeout=10) as response:
        result = json.load(response)
    return next(item for item in result['data']['items'] if item['observed_instance_id'] == SECRET['observed_instance_id'])

if __name__ == '__main__':
    assert not STATE.exists()
    before = canonical_snapshot()
    base = ['bind', '--state', str(STATE), '--herdr-executable', str(HERDR['EXE']), '--session', HERDR['SESSION'],
        '--namespace', 'pr09-installed-herdr', '--pane', 'w1:p1', '--server', SECRET['server_origin'],
        '--source-id', SECRET['source_id'], '--instance-id', SECRET['observed_instance_id'],
        '--generation', str(SECRET['generation'])]
    preview = cli('preview', base)
    assert preview['activity'] == 'idle' and not STATE.exists()
    cli('bind', base + ['--approve-selection', preview['selection']])
    first = publish('startup-done')
    view = observation_view()
    assert view['activity_state'] == 'idle'
    assert 'current_completion_ref' not in json.loads(STATE.read_text())['last_receipt']
    assert json.loads(STATE.read_text())['checkpoint']['completion_ref'] is None
    hook('working', 6)
    publish('working')
    assert observation_view()['activity_state'] == 'working'
    hook('blocked', 7)
    publish('blocked')
    assert observation_view()['activity_state'] == 'blocked'
    hook('idle', 8)
    publish('done')
    checkpoint = json.loads(STATE.read_text())['checkpoint']
    assert checkpoint['state'] == 'idle' and checkpoint['completion_ref'] is not None
    publish('done-repeated')
    assert json.loads(STATE.read_text())['checkpoint']['completion_ref'] == checkpoint['completion_ref']
    HERDR['call']('installed-fixture-rename', ['pane', 'rename', 'w1:p1', 'pr09-installed-renamed'])
    publish('renamed')
    assert json.loads(STATE.read_text())['checkpoint']['completion_ref'] == checkpoint['completion_ref']
    cli('status', ['status', '--state', str(STATE)])
    assert before == canonical_snapshot()
    with sqlite3.connect(Path(SERVER['home']) / 'nexus.db') as connection:
        # All activity in this isolated server is observational; no productive event appeared.
        event_counts = dict(connection.execute("SELECT type,count(*) FROM events WHERE type GLOB 'observation.*' GROUP BY type"))
    proof = dict(result='passed', actual_installed_cli=True, actual_herdr='0.9.5', actual_nexus='0.3.3',
        synthetic_observed_process=True, synthetic_lifecycle_hooks=True, provider_inference=False,
        source_kind='herdr', source_id=SECRET['source_id'], observed_instance_id=SECRET['observed_instance_id'],
        generation=SECRET['generation'], stages=records, canonical_unchanged=True, canonical_before=before,
        observational_event_counts=event_counts)
    (Q / 'observer-live-campaign.json').write_text(json.dumps(proof, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(result='passed', stages=len(records), canonical_unchanged=True, source_kind='herdr',
        source_id=SECRET['source_id'], observed_instance_id=SECRET['observed_instance_id'])))
