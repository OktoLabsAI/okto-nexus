"""Stop only our verified QA orchestrator after its current wave is settled."""
import json
from pathlib import Path
import time

import psutil

HERE = Path(__file__).resolve().parent
OWN = Path('C:/Users/jpamb/AppData/Local/Temp/nexus-qc09-remainder2-1o0u71_1')
PID = 53516
CREATED = 1794896909.0036757
EXE = Path('C:/Python313/python.exe')


def owned():
    process = psutil.Process(PID)
    assert process.create_time() == CREATED and Path(process.exe()) == EXE
    args = process.cmdline()
    assert args[-2:] == ['2', '--run']
    assert any(value.replace('\\', '/').endswith('qc09-installed-23/remainder.py') for value in args)
    return process


def main():
    owned()
    target = OWN / 'wave3/output/result.json'
    print(json.dumps(dict(watching=str(target), own_pid=PID)), flush=True)
    deadline = time.monotonic() + 600
    while True:
        assert time.monotonic() < deadline, 'Boundary watch expired without changing a process'
        if target.exists():
            try:
                result = json.loads(target.read_text())
            except (ValueError, OSError):
                time.sleep(.002)
                continue
            # execute() writes result only after child wait and own-tree checks.
            assert all(result['physically_exited'].values()), result['physically_exited']
            process = owned()
            process.suspend()
            family = process.children(recursive=True)
            if family:
                # Do not kill a running wave or orphan its containment watcher.
                process.resume()
                raise RuntimeError('Next wave raced boundary; no process was stopped')
            identity = dict(pid=PID, created=CREATED, executable=str(EXE))
            process.terminate()
            process.wait(timeout=15)
            record = dict(status='STOPPED_BETWEEN_WAVES', owned_orchestrator=identity,
                last_wave_result=str(target), child_pids_at_stop=[],
                physical_orchestrator_exit=not psutil.pid_exists(PID))
            (HERE / 'remainder2-boundary-stop.json').write_text(json.dumps(record, indent=2)+'\n', encoding='utf-8')
            print(json.dumps(record), flush=True)
            return
        time.sleep(.002)


if __name__ == '__main__':
    main()
