"""Read-only source qualification against the actual disposable Herdr server."""
from dataclasses import asdict
import json
import runpy

from okto_nexus.adapters.outbound.observation.herdr import HerdrCLI
from okto_nexus.adapters.outbound.observation.windows_identity import open_process_identity
from okto_nexus.application.herdr_observer import sample_source

m = runpy.run_path(r'C:\Users\jpamb\AppData\Local\Temp\pr09-herdr-live.py')
root = m['ROOT']
source = HerdrCLI(m['EXE'], m['SESSION'], environment=m['ENV'])
contract = source.contract()
binding, observation, observed_at = sample_source(source, open_process_identity,
    pane='w1:p1', namespace='pr09-disposable-installation', session=m['SESSION'])
proof = {'contract': contract, 'binding': asdict(binding), 'observation': observation.to_dict(),
         'observed_at': observed_at, 'herdr_real': True, 'observed_process_synthetic': True,
         'provider_inference': False, 'terminal_reads': False, 'control_commands': False}
(root / 'live/adapter-read-initial.json').write_text(json.dumps(proof, indent=2) + '\n', encoding='utf-8')
print(json.dumps({key: proof[key] for key in ('contract', 'observation', 'herdr_real', 'observed_process_synthetic',
                                           'provider_inference', 'terminal_reads', 'control_commands')}, indent=2))
