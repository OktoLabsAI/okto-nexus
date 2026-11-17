"""Run Node tests and rebuild packaged assets; preserve one evidence cut."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
NAME = sys.argv[1] if len(sys.argv) > 1 else 'qc05-frontend'
if re.fullmatch(r'qc[0-9a-z-]+', NAME) is None:
    raise ValueError('Choose a simple QC evidence directory name')
OUT = ROOT / 'NEXUS_QUICK_CONNECT_R1/execution' / NAME


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    if (OUT / 'qualification.json').exists():
        raise RuntimeError('Preserve the previous run; select another cut')
    pins = {str(p.relative_to(ROOT)).replace('\\', '/'): sha(p)
        for folder in ('frontend/src', 'frontend/tests') for p in (ROOT / folder).rglob('*') if p.is_file()}
    report = dict(at=datetime.now(timezone.utc).isoformat(), status='IN_PROGRESS', source_sha256=pins, commands=[])
    for name, command in [('node', ['rtk', 'proxy', 'npm', 'test']), ('build', ['rtk', 'proxy', 'npm', 'run', 'build'])]:
        started = datetime.now(timezone.utc)
        completed = subprocess.run(command, cwd=ROOT / 'frontend', capture_output=True,
            text=True, encoding='utf-8', errors='replace')
        output = completed.stdout + completed.stderr
        (OUT / (name + '.log')).write_text(output, encoding='utf-8')
        result = dict(name=name, command=command, exit_code=completed.returncode,
            seconds=(datetime.now(timezone.utc) - started).total_seconds())
        if name == 'node':
            result['totals'] = {key: int(value) for key, value in re.findall(
                r'^.*?\b(tests|suites|pass|fail|cancelled|skipped|todo) (\d+)\s*$', output, re.M)}
        report['commands'].append(result)
        (OUT / 'qualification.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(result), flush=True)
        if completed.returncode:
            return completed.returncode
    drift = [p for p, expected in pins.items() if not (ROOT / p).is_file() or sha(ROOT / p) != expected]
    static = ROOT / 'src/okto_nexus/adapters/inbound/http/static'
    report.update(status='PASS' if not drift else 'FAIL', source_drift=drift,
        static_sha256={str(p.relative_to(ROOT)).replace('\\', '/'): sha(p) for p in static.rglob('*') if p.is_file()},
        limitations=['Node/SSR, TypeScript and Vite only; no browser, screen reader, human, installed package or real harness proof.',
            'Existing bundle-size and SSR useLayoutEffect warnings are retained in logs.'])
    (OUT / 'qualification.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(status=report['status'], source_drift=drift, assets=report['static_sha256'])), flush=True)
    return 0 if not drift else 1


if __name__ == '__main__':
    sys.exit(main())
