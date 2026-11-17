"""Host supervisor; starts only a separately authorized private runtime."""
import argparse
import importlib.util
import json
from pathlib import Path
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ready', type=Path, required=True)
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location('hst_own_containment', here / 'containment.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    config = module.require_ready(args.ready)
    root = Path(config['root']).resolve()
    owner = module.Owned(root)
    child = owner.start(args.ready, root / 'fixture.py')
    print(json.dumps(dict(event='STARTED',pid=child,root=str(root))),flush=True)
    announced = False
    end = time.monotonic() + 300
    try:
        while owner.process.poll() is None and time.monotonic() < end:
            owner.sample()
            path = root / 'control/ready.json'
            if path.exists() and not announced:
                # Readiness metadata has no credential value. Never print the
                # private storage file contents or fixture stdout/stderr.
                value = json.loads(path.read_text())
                print(json.dumps(dict(event='READY',url=value['url'],root=str(root))),flush=True)
                announced = True
            time.sleep(.25)
    finally:
        result = owner.stop(force=owner.process.poll() is None)
        (root / 'control/supervisor-cleanup.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(dict(event='CLOSED',cleanup=result)),flush=True)


if __name__ == '__main__':
    main()
