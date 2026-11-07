"""Explicit generation rotation/reassociation, then actual process replacement."""
import json
import runpy
import time

m = runpy.run_path(r'C:\Users\jpamb\AppData\Local\Temp\pr09-installed-_p9t3pls\observer_live_campaign.py')
q, root, herdr = m['Q'], m['ROOT'], m['HERDR']
credential = json.loads((q / 'qualification-herdr-moved-credential.json').read_text())
m['SECRET'].clear()
m['SECRET'].update(credential)
m['SERVER']['python'] = str(root / 'qualified-v2/venv/Scripts/python.exe')
state_path = q / 'observer-moved-state.json'
assert not state_path.exists()
base = ['bind', '--state', str(state_path), '--herdr-executable', str(herdr['EXE']), '--session', herdr['SESSION'],
        '--namespace', 'pr09-installed-herdr', '--pane', 'w2:p2', '--server', credential['server_origin'],
        '--source-id', credential['source_id'], '--instance-id', credential['observed_instance_id'],
        '--generation', str(credential['generation']), '--ttl', '30']
preview = m['cli']('moved-rebind-preview', base)
m['cli']('moved-rebind', base + ['--approve-selection', preview['selection']])
run = ['run', '--state', str(state_path), '--token-env', 'NEXUS_PR09_OBSERVATION_TOKEN', '--once']
m['cli']('moved-rebound-publication', run, token=True)
before = json.loads(state_path.read_text())
assert before['sequence'] == 1 and before['checkpoint']['completion_ref'] is None and not before['invalidated']

# Only the fixture driver stops/replaces its own synthetic process. It uses its
# explicit stop file, never kill/send-keys through the product observer.
(herdr['ROOT'] / 'work/stop-fixture-1').write_text('fixture complete\n')
for index in range(20):
    result = herdr['call']('replacement-shell-' + str(index), ['pane', 'process-info', '--pane', 'w2:p2'])
    info = json.loads(result.stdout)['result']['process_info']
    if info['foreground_process_group_id'] == info['shell_pid']:
        break
    time.sleep(.25)
else:
    raise AssertionError('Synthetic process did not exit')
argv = [str(herdr['ROOT'] / 'work/codex.exe'), str(herdr['ROOT'] / 'work/stop-fixture-2')]
herdr['call']('fixture-replacement-start', ['pane', 'run', 'w2:p2', 'subprocess.run(' + repr(argv) + ')'])
for index in range(20):
    result = herdr['call']('replacement-ready-' + str(index), ['pane', 'process-info', '--pane', 'w2:p2'])
    info = json.loads(result.stdout)['result']['process_info']
    if info['foreground_process_group_id'] != info['shell_pid']:
        break
    time.sleep(.25)
else:
    raise AssertionError('Synthetic replacement did not start')
result = m['cli']('replacement-refused', run, token=True, expected=2)
after = json.loads(state_path.read_text())
assert after['invalidated'] is True and after['sequence'] == 1
assert result['code'] == 'HERDR_BINDING_CHANGED'
proof = dict(result='passed', generation=credential['generation'], source_id=credential['source_id'],
    observed_instance_id=credential['observed_instance_id'], original_pid=before['binding']['pid'],
    replacement_pid=info['foreground_process_group_id'], original_birth=before['binding']['creation_filetime'],
    sequence_before=before['sequence'], sequence_after=after['sequence'], invalidated=after['invalidated'],
    cli=result, new_generation_startup_completion_ref=before['checkpoint']['completion_ref'],
    actual_process_replacement=True, synthetic_process=True, provider_inference=False)
(q / 'observer-replacement-campaign.json').write_text(json.dumps(proof, indent=2) + '\n', encoding='utf-8')
print(json.dumps(proof))
