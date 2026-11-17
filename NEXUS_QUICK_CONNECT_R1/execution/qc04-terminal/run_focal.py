"""Finite owned HTTP/SQLite qualification; never installs into the PR27 prefix."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
PYTHON = Path('C:/Users/jpamb/AppData/Local/Temp/nexus-ui-r3-harness-pr27-gsg_twh1/venv/Scripts/python.exe')
SOURCES = [
    'src/okto_nexus/application/terminal_connection.py',
    'src/okto_nexus/adapters/inbound/cli/quick_connect_outcome.py',
    'src/okto_nexus/domain/quick_connect.py',
    'src/okto_nexus/application/connection_public_ids.py',
    'src/okto_nexus/application/connection_project_context.py',
    'src/okto_nexus/application/connection_setup.py',
    'src/okto_nexus/adapters/inbound/http/runtime_v1.py',
    'src/okto_nexus/domain/connection_public_ids.py',
    'tests/execution_r4/test_terminal_connect.py',
    'tests/execution_r4/test_public_connection_ids.py',
    'tests/execution_r4/test_local_realization.py',
    'tests/execution_r4/test_local_installation_check.py',
    'tests/execution_r4/test_binding_operator.py',
    'tests/quick_connect/test_quick_connect_outcome.py',
    'tests/quick_connect/test_terminal_public_connection.py',
]


def pins():
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCES}


before = pins()
code = (
    'import sys,json;sys.path.insert(0,' + repr(str(ROOT / 'src')) + ');'
    'import okto_nexus,nexus_connector_core;'
    'print("SOURCE_PROVENANCE "+json.dumps({"python":sys.executable,"nexus":okto_nexus.__file__,"core":nexus_connector_core.__file__}),flush=True);'
    'import pytest;raise SystemExit(pytest.main(["-q","tests/quick_connect/test_quick_connect_outcome.py","tests/quick_connect/test_terminal_public_connection.py"]))'
)
argv = [str(PYTHON), '-I', '-B', '-X', 'utf8', '-c', code]
started = time.monotonic()
result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, encoding='utf-8')
elapsed = time.monotonic() - started
(HERE / 'focal-stdout.txt').write_text(result.stdout, encoding='utf-8')
(HERE / 'focal-stderr.txt').write_text(result.stderr, encoding='utf-8')
after = pins()
record = dict(exit_code=result.returncode, duration_seconds=elapsed, argv=argv, cwd=str(ROOT),
    source_before=before, source_after=after, source_drift=[name for name in before if before[name] != after[name]],
    stdout_sha256=hashlib.sha256(result.stdout.encode()).hexdigest(),
    stderr_sha256=hashlib.sha256(result.stderr.encode()).hexdigest(),
    limits=['Source-first Nexus with qualified PR27 Core; no prefix installation',
            'Owned TestClient ASGI/SQLite and synthetic installation/model peers, not actual provider/native lifecycle'])
(HERE / 'focal-run.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
print(result.stdout)
print(json.dumps(dict(exit_code=result.returncode, duration_seconds=elapsed, source_drift=record['source_drift'])))
sys.exit(result.returncode)
