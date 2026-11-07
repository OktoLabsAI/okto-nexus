"""Final read-only canonical/OBS evidence before intentional service cleanup."""
from collections import Counter, defaultdict
import json
import runpy
import sqlite3
from pathlib import Path

m = runpy.run_path(r'C:\Users\jpamb\AppData\Local\Temp\pr09-installed-_p9t3pls\observer_live_campaign.py')
q = m['Q']
before = json.loads((q / 'observer-live-campaign.json').read_text())['canonical_before']
after = m['canonical_snapshot']()
assert before == after
with sqlite3.connect(Path(m['SERVER']['home']) / 'nexus.db') as connection:
    records = [dict(type=kind, payload=json.loads(payload)) for kind, payload in
               connection.execute('SELECT type,payload FROM events WHERE type GLOB ?', ('observation.*',))]
selected = [row for row in records if row['payload']['source_id'] == 'obs_src_0000000000000006']
counts = defaultdict(Counter)
for row in selected:
    counts[row['payload']['generation']][row['type']] += 1
assert counts[7] == Counter({'observation.activity': 3, 'observation.completion': 1})
assert counts[9] == counts[11] == Counter({'observation.activity': 1})
audit = [json.loads(line) for line in (q / 'observer-command-audit.jsonl').read_text().splitlines()]
assert set(row['command'] for row in audit) == {'version', 'schema', 'status', 'snapshot', 'process_info'}
view = m['observation_view']()
assert view['generation'] == 11 and view['freshness'] == 'stale' and view['activity_state'] == 'unknown'
proof = dict(result='passed', canonical_tables=len(before), canonical_before=before, canonical_after=after,
    canonical_unchanged=True, observation_event_counts={str(k): dict(v) for k, v in counts.items()},
    repeated_completion_events=1, startup_completion_events_after_rotations=0,
    source_view=view, observer_command_calls=len(audit), command_counts=dict(Counter(row['command'] for row in audit)),
    observer_control_commands=0, observer_terminal_reads=0)
(q / 'observer-event-proof.json').write_text(json.dumps(proof, indent=2) + '\n', encoding='utf-8')
print(json.dumps({key: proof[key] for key in ('result', 'canonical_tables', 'canonical_unchanged',
    'observation_event_counts', 'observer_command_calls', 'observer_control_commands', 'observer_terminal_reads')}))
