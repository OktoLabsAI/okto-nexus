"""Finite source-first pure QC021 test run; no installation or provider."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
PYTHON = 'C:/Users/jpamb/AppData/Local/Temp/nexus-ui-r3-harness-pr27-gsg_twh1/venv/Scripts/python.exe'
SOURCES = ['src/okto_nexus/application/connection_public_ids.py', 'src/okto_nexus/application/endpoints.py', 'src/okto_nexus/application/connection_project_context.py', 'src/okto_nexus/application/connection_setup.py', 'tests/execution_r4/test_public_id_retirement.py', 'tests/execution_r4/test_public_connection_ids.py']


def pins():
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCES}


before = pins()
code = ('import sys;sys.path.insert(0,' + repr(str(ROOT / 'src')) + ');'
    'import okto_nexus;print("SOURCE_PROVENANCE",sys.executable,okto_nexus.__file__,flush=True);'
    'import pytest;raise SystemExit(pytest.main(["-q","tests/execution_r4/test_public_id_retirement.py","--junitxml=NEXUS_QUICK_CONNECT_R1/execution/qc07-public-id-occupancy/pytest.xml"]))')
argv = [PYTHON, '-I', '-B', '-X', 'utf8', '-c', code]
started = time.monotonic()
result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, encoding='utf-8', timeout=120)
after = pins()
record = dict(exit_code=result.returncode, duration_seconds=time.monotonic() - started, argv=argv,
    source_before=before, source_after=after, source_drift=[name for name in before if before[name] != after[name]])
(HERE / 'focal-stdout.txt').write_text(result.stdout, encoding='utf-8')
(HERE / 'focal-stderr.txt').write_text(result.stderr, encoding='utf-8')
(HERE / 'focal-run.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
print(result.stdout)
print(json.dumps(dict(exit_code=result.returncode, source_drift=record['source_drift'])))
sys.exit(result.returncode)
