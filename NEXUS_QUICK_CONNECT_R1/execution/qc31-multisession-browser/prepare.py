"""Copy the full protocol helper function and fake source verbatim by AST."""
import ast
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
root = Path(tempfile.mkdtemp(prefix='nexus-qc31-multisession-'))
for name in ('home', 'project', 'provider-home', 'control', 'cwd', 'tmp', 'os-home', 'appdata', 'localappdata', 'helpers'):
    (root / name).mkdir()
source_path = REPO / 'tests/execution_r4/test_canonical_native_protocol_regressions.py'
source = source_path.read_text()
node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == 'install_native')
function = ast.get_source_segment(source, node)
fake_path = REPO / 'tests/test_harness_codex_connector.py'
fake_text = fake_path.read_text()
fake_node = next(n for n in ast.parse(fake_text).body if isinstance(n, ast.Assign) and
                 any(isinstance(t, ast.Name) and t.id == '_FAKE_SERVER_SOURCE' for t in n.targets))
fake = ast.literal_eval(fake_node.value)
helper = 'import asyncio\nimport json\nimport sys\nimport time\n\n' + function + '\n\n_FAKE_SERVER_SOURCE = ' + repr(fake) + '\n'
(root / 'helpers/protocol_fixture.py').write_text(helper, encoding='utf-8')
pins = dict(full_helper_source=str(source_path), full_helper_source_sha256=hashlib.sha256(source_path.read_bytes()).hexdigest(),
    full_install_native_function_sha256=hashlib.sha256(function.encode()).hexdigest(),
    fake_source_file=str(fake_path), fake_source_file_sha256=hashlib.sha256(fake_path.read_bytes()).hexdigest(),
    fake_protocol_source_sha256=hashlib.sha256(fake.encode()).hexdigest(),
    extracted_helper_sha256=hashlib.sha256((root / 'helpers/protocol_fixture.py').read_bytes()).hexdigest(),
    method='Complete original install_native function and literal fake source, no protocol/body edits or SQL fixture imports.')
(root / 'helper-pins.json').write_text(json.dumps(pins, indent=2) + '\n')
(HERE / 'allocation.json').write_text(json.dumps(dict(root=str(root), prefix='C:/Users/jpamb/AppData/Local/Temp/nexus-qc-r1-package-t24_dnfc/venv',
    python='C:/Users/jpamb/AppData/Local/Temp/nexus-qc-r1-package-t24_dnfc/venv/Scripts/python.exe',
    stop=str(root / 'control/stop'), ready=str(root / 'control/ready.json'), final=str(root / 'control/final.json'),
    helper_pins=pins, prepared_only=True), indent=2) + '\n')
print(json.dumps(dict(root=str(root), helper_pins=pins)))
