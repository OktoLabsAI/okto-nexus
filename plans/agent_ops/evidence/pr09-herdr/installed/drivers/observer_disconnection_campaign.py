"""Stop/restart only the disposable Herdr; require a fresh snapshot/rebinding."""
import json
from pathlib import Path
import runpy
import subprocess
import time
import psutil

m = runpy.run_path(r'C:\Users\jpamb\AppData\Local\Temp\pr09-installed-_p9t3pls\observer_live_campaign.py')
q, root, herdr = m['Q'], m['ROOT'], m['HERDR']
credential = json.loads((q / 'qualification-herdr-reconnect-credential.json').read_text())
m['SECRET'].clear()
m['SECRET'].update(credential)
m['SERVER']['python'] = str(root / 'qualified-v2/venv/Scripts/python.exe')
state_path = q / 'observer-reconnect-state.json'
before = json.loads(state_path.read_text())
assert before['sequence'] == 1 and not before['invalidated']
run = ['run', '--state', str(state_path), '--token-env', 'NEXUS_PR09_OBSERVATION_TOKEN', '--once']
launcher = json.loads((herdr['ROOT'] / 'live/launcher.json').read_text())
parent = psutil.Process(launcher['pid'])
owned = [parent, *parent.children(recursive=True)]
assert any(process.pid == before['binding']['pid'] for process in owned)
assert any(Path(process.exe()).resolve() == herdr['EXE'].resolve() for process in owned)
herdr['call']('fixture-stop-for-reconnect', ['server', 'stop'])
gone, alive = psutil.wait_procs(owned, timeout=10)
assert not alive
unavailable = m['cli']('source-disconnected', run, token=True, expected=2)
assert unavailable['code'] == 'HERDR_SERVER_UNAVAILABLE'
disconnected_state = json.loads(state_path.read_text())
assert disconnected_state['sequence'] == 1 and not disconnected_state['invalidated']

# Preserve the existing isolated configuration: updates and agent resume remain
# disabled. No personal profiles or native provider client are loaded.
with (herdr['ROOT'] / 'live/restarted-server.stdout.txt').open('wb') as out, (herdr['ROOT'] / 'live/restarted-server.stderr.txt').open('wb') as err:
    child = subprocess.Popen(['rtk', 'proxy', str(herdr['EXE']), '--session', herdr['SESSION'], 'server'],
        cwd=herdr['ROOT'] / 'work', env=herdr['ENV'], stdout=out, stderr=err,
        creationflags=subprocess.CREATE_NO_WINDOW)
(herdr['ROOT'] / 'live/restarted-launcher.json').write_text(json.dumps(dict(pid=child.pid, session=herdr['SESSION'])))
for index in range(20):
    status = herdr['call']('restarted-status-' + str(index), ['status', 'server', '--json'])
    if status.returncode == 0 and json.loads(status.stdout).get('running') is True:
        break
    if child.poll() is not None:
        raise AssertionError('Disposable restart failed')
    time.sleep(.25)
else:
    raise AssertionError('Disposable restart was not ready')
snapshot = herdr['call']('raw-restored-snapshot', ['api', 'snapshot'])
restored = json.loads(snapshot.stdout)['result']['snapshot']
assert any(pane['pane_id'] == 'w2:p2' for pane in restored['panes'])
assert not restored['agents']
argv = [str(herdr['ROOT'] / 'work/codex.exe'), str(herdr['ROOT'] / 'work/stop-fixture-3')]
herdr['call']('fixture-restored-process-start', ['pane', 'run', 'w2:p2',
    'import subprocess; subprocess.run(' + repr(argv) + ')'])
for index in range(20):
    result = herdr['call']('restored-process-' + str(index), ['pane', 'process-info', '--pane', 'w2:p2'])
    info = json.loads(result.stdout)['result']['process_info']
    if info['foreground_process_group_id'] != info['shell_pid']:
        break
    time.sleep(.25)
else:
    raise AssertionError('Restored synthetic process was not ready')
reconnected = m['cli']('source-reconnected-new-occupant', run, token=True, expected=2)
after = json.loads(state_path.read_text())
assert reconnected['code'] == 'HERDR_BINDING_CHANGED'
assert after['sequence'] == 1 and after['invalidated'] is True and after['pending'] is None
audit = [json.loads(line) for line in (q / 'observer-command-audit.jsonl').read_text().splitlines()]
assert [row['command'] for row in audit[-8:]] == [
    'version', 'schema', 'status', 'status', 'process_info', 'snapshot', 'status', 'process_info']
proof = dict(result='passed', actual_source_stop_restart=True, old_processes_exited=sorted(process.pid for process in gone),
    disconnected=unavailable, invalidated_during_unavailability=disconnected_state['invalidated'],
    reconnected=reconnected, invalidated_after_new_identity=after['invalidated'],
    sequence_before=before['sequence'], sequence_after=after['sequence'],
    no_backlog_replayed=True, source_snapshot_read_after_reconnect=True,
    previous_occupant_pid=before['binding']['pid'], new_occupant_pid=info['foreground_process_group_id'],
    synthetic_observed_process=True, provider_inference=False)
(q / 'observer-disconnection-campaign.json').write_text(json.dumps(proof, indent=2) + '\n', encoding='utf-8')
print(json.dumps(proof))
