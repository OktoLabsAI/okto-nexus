"""Copy curated inert fixture into its own Temp, changing paths/logging only."""
from pathlib import Path
import json
import tempfile

root = Path(__file__).resolve().parents[2]
evidence = root / 'NEXUS_UI_R1/execution/evidence/pr07-panel09-lost-response'
evidence.mkdir(exist_ok=True)
own = Path(tempfile.mkdtemp(prefix='nexus-ui-panel09-runner-'))
source = root / 'NEXUS_UI_R1/execution/evidence/pr04-browser/human-vmhGy86G'
base = (source.parent / 'fixture.py').read_text(encoding='utf8')
base = base.replace('ROOT = Path(__file__).resolve().parents[4]', f'ROOT = Path({str(root)!r})')
(own / 'fixture.py').write_text(base, encoding='utf8')
human = (source / 'human-fixture.py').read_text(encoding='utf8')
human = human.replace('ROOT=HERE.parents[3]', f'ROOT=Path({str(root)!r})')
human = human.replace('p.relative_to(ROOT).as_posix()', 'str(p)')
human = human.replace('summary=dict(decisions=', '''summary=dict(
                input_operations=[dict(r) for r in c.execute("SELECT operation_id,action,actor_agent_id,subject_agent_id,session_id FROM execution_operations WHERE action='input.provide'")],
                matching_outbox=c.execute("SELECT COUNT(*) FROM delivery_outbox WHERE operation_id IN (SELECT operation_id FROM execution_operations WHERE action='input.provide')").fetchone()[0], decisions=''')
(own / 'human-fixture.py').write_text(human, encoding='utf8')
live = (source / 'human-live-fixture.py').read_text(encoding='utf8')
# Logging must not stop the canonical heartbeat after successful renew/applied.
live = live.replace("grant['valid_until_server']", "grant.get('valid_until_server')")
(own / 'human-live-fixture.py').write_text(live, encoding='utf8')
(evidence / 'allocation.json').write_text(json.dumps({'runner_root':str(own)},indent=2),encoding='utf8')
print(own)
