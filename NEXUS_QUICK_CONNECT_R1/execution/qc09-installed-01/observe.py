"""Read-only progress and descendant identities; never reads process command lines."""
import json
from pathlib import Path
import time

import psutil

HERE = Path(__file__).resolve().parent
for index in (0, 1):
    ready = json.loads((HERE / f'shard{index}-ready.json').read_text())
    output = Path(ready['output'])
    record = HERE / f'shard{index}-observed-processes.json'
    previous = json.loads(record.read_text()) if record.exists() else {}
    tracked = set(map(int, previous)) | {ready['child_pid']}
    processes = {p.pid: p.info for p in psutil.process_iter(['pid', 'ppid', 'create_time'])}
    while True:
        more = {pid for pid, p in processes.items() if p['ppid'] in tracked}
        if more <= tracked:
            break
        tracked |= more
    alive = []
    for pid in tracked:
        current = processes.get(pid)
        if current is None:
            continue
        old = previous.get(str(pid))
        if old and old['create_time'] != current['create_time']:
            continue  # Never attribute a reused PID to the campaign.
        previous[str(pid)] = dict(current, last_observed=time.time())
        alive.append(pid)
    record.write_text(json.dumps(previous, indent=2)+'\n', encoding='utf-8')
    text = (output / 'stdout.txt').read_text(encoding='utf-8')
    print(json.dumps(dict(shard=index, pass_lines=text.count(' PASSED '), fail_lines=text.count(' FAILED '),
        skip_lines=text.count(' SKIPPED '), live_observed_descendants=alive, last_lines=text.splitlines()[-2:])))
