"""Prepare an explicit binding; all Herdr calls here are read-only."""
import json
import runpy

m = runpy.run_path(r'C:\Users\jpamb\AppData\Local\Temp\pr09-installed-_p9t3pls\observer_live_campaign.py')
q, root, herdr = m['Q'], m['ROOT'], m['HERDR']
credential = json.loads((q / 'qualification-herdr-reconnect-credential.json').read_text())
m['SECRET'].clear()
m['SECRET'].update(credential)
m['SERVER']['python'] = str(root / 'qualified-v2/venv/Scripts/python.exe')
state = q / 'observer-reconnect-state.json'
assert not state.exists()
base = ['bind', '--state', str(state), '--herdr-executable', str(herdr['EXE']), '--session', herdr['SESSION'],
    '--namespace', 'pr09-installed-herdr', '--pane', 'w2:p2', '--server', credential['server_origin'],
    '--source-id', credential['source_id'], '--instance-id', credential['observed_instance_id'],
    '--generation', str(credential['generation']), '--ttl', '30']
preview = m['cli']('reconnect-preview', base)
m['cli']('reconnect-bind', base + ['--approve-selection', preview['selection']])
m['cli']('reconnect-initial-publication', ['run', '--state', str(state), '--token-env',
    'NEXUS_PR09_OBSERVATION_TOKEN', '--once'], token=True)
saved = json.loads(state.read_text())
assert saved['sequence'] == 1 and not saved['invalidated']
(q / 'observer-reconnect-before.json').write_text(json.dumps({
    'generation': saved['generation'], 'sequence': 1, 'binding': saved['binding'],
    'checkpoint': saved['checkpoint'], 'last_receipt': saved['last_receipt']}, indent=2), encoding='utf-8')
print(json.dumps(dict(result='prepared', generation=saved['generation'], sequence=saved['sequence'],
                     observed_state=saved['checkpoint']['state'])))
