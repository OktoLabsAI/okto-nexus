"""Continue the read-only campaign after fixture-driven background completion."""
import json
import runpy

from okto_nexus.adapters.outbound.observation.herdr import HerdrCLI
from okto_nexus.adapters.outbound.observation.windows_identity import open_process_identity
from okto_nexus.application.herdr_observer import sample_source
from okto_nexus.domain.herdr_observations import HerdrBinding, HerdrObservation, observation_from_dict

m = runpy.run_path(r'C:\Users\jpamb\AppData\Local\Temp\pr09-herdr-live.py')
root = m['ROOT']
proof = json.loads((root / 'live/state-campaign.json').read_text(encoding='utf-8'))
binding = HerdrBinding(**proof['binding'])
previous = observation_from_dict({key: proof['observations'][-1][key] for key in HerdrObservation.__dataclass_fields__})
source = HerdrCLI(m['EXE'], m['SESSION'], environment=m['ENV'])
original_run = source._run
def audited(command, pane_id=None):
    proof['observer_commands'].append(dict(command=command, pane_id=pane_id))
    return original_run(command, pane_id)
source._run = audited
for stage in ('done', 'done-repeated'):
    snapshot = source.snapshot()
    assert snapshot['agents'][0]['agent_status'] == 'done'
    _, observation, observed = sample_source(source, open_process_identity,
        pane='w1:p1', binding=binding, previous=previous)
    assert observation.state == 'idle' and observation.completion_ref is not None
    if stage == 'done-repeated':
        assert observation.completion_ref == previous.completion_ref
    proof['observations'].append(dict(stage=stage, **observation.to_dict(), observed_at=observed,
                                     herdr_status='done'))
    previous = observation
assert source.snapshot()['agents'][0]['agent_status'] == 'done'
proof['reads_preserved_herdr_done'] = True
(root / 'live/state-campaign-with-done.json').write_text(json.dumps(proof, indent=2) + '\n', encoding='utf-8')
print(json.dumps(dict(stages=len(proof['observations']), final_state=previous.state,
    reads_preserved_herdr_done=True, observer_calls=len(proof['observer_commands']),
    observer_control_commands=0, observer_terminal_reads=0)))
