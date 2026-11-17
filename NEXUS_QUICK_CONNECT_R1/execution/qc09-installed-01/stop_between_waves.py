"""Prevent further derivative waves only when the verified orchestrator has no children."""
import json
from pathlib import Path
import sys
import time

import psutil

HERE = Path(__file__).resolve().parent
index = int(sys.argv[1])
readyfile = HERE / f'filtered{index}-ready.json'
ready = json.loads(readyfile.read_text())
pid = ready['orchestrator_pid']
process = psutil.Process(pid)
born = process.create_time()
assert abs(born - readyfile.stat().st_mtime) < 30
assert 'remainder_filtered.py' in ' '.join(process.cmdline()) and process.cmdline()[-1] == str(index)
print(json.dumps(dict(shard=index, orchestrator_pid=pid, create_time=born, waiting='No active own child subtree')), flush=True)
deadline = time.monotonic() + 1800
while time.monotonic() < deadline:
    try:
        process = psutil.Process(pid)
        if process.create_time() != born:
            break
        if process.children(recursive=True):
            time.sleep(.05)
            continue
        # Recheck atomically while parent cannot spawn another wave. Resume if
        # it won the race and already created its next own child.
        process.suspend()
        if process.children(recursive=True):
            process.resume()
            time.sleep(.05)
            continue
        process.terminate()
        process.wait(timeout=10)
        record = dict(shard=index, status='ORCHESTRATION_ENDED_BETWEEN_WAVES', pid=pid, create_time=born,
            physically_exited=True, no_child_subtree_at_stop=True,
            scope='No test body or fixture was interrupted by this stop; completed/hung wave records remain authoritative')
        (HERE / f'filtered{index}-stop.json').write_text(json.dumps(record, indent=2)+'\n', encoding='utf-8')
        print(json.dumps(record), flush=True)
        break
    except psutil.NoSuchProcess:
        print(json.dumps(dict(shard=index, already_exited=True)), flush=True)
        break
