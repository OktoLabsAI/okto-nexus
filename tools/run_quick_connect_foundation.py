"""Record the source-only QC foundation check without changing any prefix."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
NAME = sys.argv[1] if len(sys.argv) > 1 else 'qc01-foundation'
if re.fullmatch(r'qc[0-9a-z-]+', NAME) is None:
    raise ValueError('Choose a simple QC evidence directory name')
OUT = ROOT / 'NEXUS_QUICK_CONNECT_R1/execution' / NAME
PYTHON = Path(r'C:\Users\jpamb\AppData\Local\Temp\nexus-ui-r3-harness-pr27-gsg_twh1\venv\Scripts\python.exe')
NODES = [
    'tests/quick_connect/test_quick_connect_contracts.py',
    'tests/quick_connect/test_connect_arguments.py',
    'tests/quick_connect/test_connect_dispatch.py',
    'tests/quick_connect/test_git_project_hint.py',
    'tests/quick_connect/test_git_project_trust.py',
    'tests/quick_connect/test_quick_connect_id_choices.py',
    'tests/quick_connect/test_quick_connect_project.py',
    'tests/execution_r4/test_cli_http_only.py',
]
SOURCES = [
    'domain/quick_connect.py',
    'adapters/inbound/cli/connect_arguments.py',
    'adapters/inbound/cli/main.py',
    'adapters/inbound/cli/connect.py',
    'adapters/inbound/cli/quick_connect_project.py',
    'adapters/inbound/cli/quick_connect_ids.py',
    'adapters/outbound/git_project_hint.py',
]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    if (OUT / 'qualification.json').exists():
        raise RuntimeError('Preserve this run; choose a new evidence directory for a new cut')
    command = ['rtk', 'proxy', str(PYTHON), '-B', '-X', 'utf8', '-m', 'pytest', '-q',
        *NODES, '--junitxml=' + str(OUT / 'pytest.xml')]
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
        encoding='utf-8', errors='replace')
    (OUT / 'pytest.log').write_text(completed.stdout + completed.stderr, encoding='utf-8')
    paths = [ROOT / 'src/okto_nexus' / p for p in SOURCES] + [ROOT / p for p in NODES]
    record = dict(recorded_at=datetime.now(timezone.utc).isoformat(),
        scope='Source-only pure DTO/grammar/dispatch/Git fixtures/project and public-ID decisions. Not installed QC or real harness.',
        command=command, cwd=str(ROOT), exit_code=completed.returncode,
        python=str(PYTHON), dependency_environment='Frozen PR27 Core 0.0.14, interpreter read-only with -B; Nexus imported from checkout via pytest pythonpath.',
        source_pins={str(p.relative_to(ROOT)).replace('\\', '/'): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        antecedents=[
            'Legacy explicit stdio dispatch initially lost its HTTP migration hint: 88 PASS/1 FAIL; restored only for explicit old entries, unknown typo remains useful.',
            'Root .venv collection lacks Core user_service_definition; no dependency or user install changed. Re-ran with the frozen PR27 dependency interpreter.',
            'Additional unit-test red runs and exact source pins are preserved in the per-component evidence directories.',
        ], limitations=['No provider, service lifecycle, real PTY, browser, human, installed 0.3.6 or OS matrix qualification.'])
    (OUT / 'qualification.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(exit_code=completed.returncode, report=str(OUT), output_tail=completed.stdout[-1600:])))
    return completed.returncode


if __name__ == '__main__':
    sys.exit(main())
