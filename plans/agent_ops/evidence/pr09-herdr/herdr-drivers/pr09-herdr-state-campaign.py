"""Real Herdr, synthetic process/hooks; fixture control is outside the adapter."""
from dataclasses import asdict
import json
import runpy

from okto_nexus.adapters.outbound.observation.herdr import HerdrCLI
from okto_nexus.adapters.outbound.observation.windows_identity import open_process_identity
from okto_nexus.application.herdr_observer import sample_source

m = runpy.run_path(r'C:\Users\jpamb\AppData\Local\Temp\pr09-herdr-live.py')
root, call = m['ROOT'], m['call']
source = HerdrCLI(m['EXE'], m['SESSION'], environment=m['ENV'])
audit = []
original_run = source._run
def audited(command, pane_id=None):
    audit.append({'command': command, 'pane_id': pane_id})
    return original_run(command, pane_id)
source._run = audited
source.contract()
binding, previous, observed_at = sample_source(source, open_process_identity,
    pane='w1:p1', namespace='pr09-state-campaign', session=m['SESSION'])
assert previous.state == 'working'
observations = [dict(stage='initial-working', **previous.to_dict(), observed_at=observed_at)]

def capture(stage):
    global previous
    _, observation, observed = sample_source(source, open_process_identity,
        pane='w1:p1', binding=binding, previous=previous)
    observations.append(dict(stage=stage, **observation.to_dict(), observed_at=observed))
    previous = observation
    call('raw-' + stage, ['api', 'snapshot'])
    return observation

for seq, state in [(2, 'blocked'), (3, 'idle')]:
    call('fixture-state-' + state, ['pane', 'report-agent', 'w1:p1', '--source', 'nexus-pr09-fixture',
         '--agent', 'nexus-pr09-fixture', '--state', state, '--seq', str(seq)])
    obs = capture(state)
    assert obs.state == state
    if state == 'blocked':
        assert obs.completion_ref is None
    else:
        assert obs.completion_ref is not None
completion_ref = previous.completion_ref
assert capture('idle-repeated').completion_ref == completion_ref
call('fixture-pane-rename', ['pane', 'rename', 'w1:p1', 'pr09-renamed'])
assert capture('renamed').completion_ref == completion_ref
call('fixture-state-working-again', ['pane', 'report-agent', 'w1:p1', '--source', 'nexus-pr09-fixture',
     '--agent', 'nexus-pr09-fixture', '--state', 'working', '--seq', '4'])
assert capture('working-again').completion_ref is None
assert set(row['command'] for row in audit) == {'version', 'schema', 'status', 'process_info', 'snapshot'}
proof = dict(real_herdr=True, synthetic_process=True, synthetic_lifecycle_hooks=True, provider_inference=False,
             binding=asdict(binding), observations=observations, observer_commands=audit,
             observer_terminal_reads=0, observer_control_commands=0)
(root / 'live/state-campaign.json').write_text(json.dumps(proof, indent=2) + '\n', encoding='utf-8')
print(json.dumps(dict(stages=[dict(stage=row['stage'], state=row['state'], completion_ref=row['completion_ref'])
                             for row in observations], observer_calls=len(audit), terminal_reads=0, control_commands=0), indent=2))
