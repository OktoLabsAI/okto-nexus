"""Installed CLI version observation only; no Server/daemon/runtime acceptance."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from okto_nexus_connector.platform.paths import state_file
from okto_nexus_connector.storage.state_store import ConnectorState, ExecutionExecutorRecord, StateStore

binary = Path('C:/Users/jpamb/.local/bin/claude.exe')
assert binary.is_file()
root = Path(tempfile.mkdtemp(prefix='connector-observation-real-'))
store = StateStore(state_file(root))
state = ConnectorState(connector_id='local-probe-fixture')
state.execution_executors.append(ExecutionExecutorRecord('probe-fixture', state.connector_id,
    'subject', 'registration-fixture', 'Local version observation', executor_id='executor-fixture', state='REGISTERED'))
store.save(state)
env = dict(os.environ, PATH=str(binary.parent)+os.pathsep+os.environ.get('PATH', ''))
cli = Path(sys.executable).with_name('okto-nexus-connector.exe')
def call(*args, expected=0):
    result = subprocess.run(['rtk', 'proxy', str(cli), '--state-dir', str(root), '--json', '--non-interactive', *args],
                            env=env, capture_output=True, text=True, timeout=90)
    assert result.returncode == expected, result.stdout + result.stderr
    return json.loads(result.stdout)
call('executor', 'configure-discovery', '--server-id', 'probe-fixture', '--harness-root', str(binary.parent))
before = call('discover', '--server-id', 'probe-fixture')
row = next(r for r in before['availability']['rows'] if r['adapter_id']=='claude_stream' and r['candidate_ref'])
assert row['state']=='NOT_PROBED', row
args = ('executor','probe','--server-id','probe-fixture','--harness','claude_stream',
        '--candidate-ref',row['candidate_ref'],'--inventory-revision',before['availability']['executor_revision'])
observed = call(*args)
after = call('discover', '--server-id', 'probe-fixture')
ready = next(r for r in after['availability']['rows'] if r['candidate_ref']==row['candidate_ref'])
assert ready['state']=='READY_FOR_RUNTIME' and ready['version']=='2.1.282', ready
assert after['availability']==observed['availability']
assert observed['runtime_authorized'] is False and observed['publication_pending'] is True
stale = call(*args, expected=1)
assert stale['error']['code']=='STALE_GENERATION', stale
assert not store.load().execution_bindings and not store.load().runtime_intents
report = dict(provider='claude_stream', version=ready['version'],
    binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
    before_state=row['state'], after_state=ready['state'],
    runtime_authorized=False, publication_pending=True, readiness_override=False,
    stale_selection_refused=True, actual_registered_server=False,
    actual_runtime_opened=False, independent_hosts=False)
Path('C:/Users/jpamb/AppData/Local/Temp/connector-observation-real-claude-probe.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report))
