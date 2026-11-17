"""Byte-identical participant fixtures; installed application imports only."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
root=Path(tempfile.mkdtemp(prefix='nexus-qc29-participant-')).resolve()
previous=Path('C:/Users/jpamb/AppData/Local/Temp/nexus-qc24-namespace-h8li_lxe')
shutil.copytree(previous/'after',root/'after',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
shutil.copyfile(previous/'pytest.ini',root/'pytest.ini')
fixtures={}
for name in ('test_participant_init.py','test_participant_launch.py'):
    source=REPO/'tests/execution_r4'/name
    target=root/'after/tests/execution_r4'/name
    shutil.copyfile(source,target)
    fixtures[name]=hashlib.sha256(source.read_bytes()).hexdigest()
    assert source.read_bytes()==target.read_bytes()
pins={p.relative_to(REPO).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
    for directory in ('src','tests','docs') for p in (REPO/directory).rglob('*')
    if p.is_file() and '__pycache__' not in p.parts}
(root/'source-pins.json').write_text(json.dumps(pins,indent=2))
(HERE/'allocation.json').write_text(json.dumps(dict(root=str(root),fixtures=fixtures),indent=2))
runner=(HERE.parent/'qc24-namespace-scenarios/run.py').read_text()
runner=runner.replace("nodes=[('namespace','tests/execution_r4/test_qc24_namespace_http.py')]",
    "nodes=[('init','tests/execution_r4/test_participant_init.py'),('launch','tests/execution_r4/test_participant_launch.py')]")
runner=runner.replace("record=dict(label=label,argv=command", "if label=='launch':\n        command.extend(['-k','test_client_configuration_selection_preserves_daemon_and_file_boundary or test_cli_saved_plan_is_passive_and_replay_does_not_launch'])\n    record=dict(label=label,argv=command")
(HERE/'run.py').write_text(runner)
assert not (root/'after/src').exists()
print(json.dumps(dict(root=str(root),fixture_hashes=fixtures,init='entire file',launch='selection3 + passive replay1')))
