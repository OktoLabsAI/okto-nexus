"""Verify affected HTTP/verification callers against the installed campaign wheel."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'plans/r4_execution/evidence'
artifacts = json.loads((OUT / 'ns15-03-publication-artifacts.json').read_text())
work = Path(artifacts['nexus']['wheel']).parents[1]
python = 'C:/Users/jpamb/AppData/Local/Temp/okto-r4-migration-resume-bkj6ies1/venv313/Scripts/python.exe'
paths = [ROOT / 'tests' / name for name in ('execution_r4/test_canonical_result_artifact.py',)]
args = ['-c', str(work / 'pytest.ini'), '--rootdir=' + str(ROOT / 'tests'),
        '--confcutdir=' + str(ROOT / 'tests'), '-o', 'asyncio_mode=auto',
        '-o', 'asyncio_default_fixture_loop_scope=function', *map(str, paths), '-q', '--tb=short',
        '--junitxml=' + str(OUT / 'ns15-03-publication-artifact.xml')]
command = ['rtk', 'proxy', python, '-I', '-c', 'import pytest; raise SystemExit(pytest.main(' + repr(args) + '))']
with (OUT / 'ns15-03-publication-artifact.log').open('w', encoding='utf-8') as log:
    result = subprocess.run(command, cwd=work, stdout=log, stderr=subprocess.STDOUT)
(OUT / 'ns15-03-publication-artifact.json').write_text(json.dumps(dict(
    cwd=str(work), artifacts=artifacts, command=command, exit_code=result.returncode,
    test_hashes={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}), indent=2) + '\n')
print((OUT / 'ns15-03-publication-artifact.log').read_text()[-4500:])
raise SystemExit(result.returncode)
