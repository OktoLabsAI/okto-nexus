import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import zipfile

ROOT = Path('D:/Projetos/Techridy/okto-nexus-connector-core')
HERE = Path(__file__).parent
Q = Path('C:/Users/jpamb/AppData/Local/Temp/r3-cooperative-drain-09ucmgsr/venv/Scripts/python.exe')
snapshot = HERE / 'candidate' / 'snapshot'
snapshot.mkdir(parents=True)
for directory in ('src', 'tests'):
    shutil.copytree(ROOT / directory, snapshot / directory,
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.egg-info'))
for name in ('pyproject.toml', 'README.md', 'LICENSE'):
    shutil.copy2(ROOT / name, snapshot / name)
def inputs(base):
    return {str(path.relative_to(base)).replace('\\', '/'): hashlib.sha256(path.read_bytes()).hexdigest()
            for directory in ('src', 'tests') for path in (base / directory).rglob('*')
            if path.is_file() and '__pycache__' not in path.parts
            and not any(part.endswith('.egg-info') for part in path.parts)}
before = inputs(ROOT)
assert before == inputs(snapshot)
(HERE / 'candidate' / 'inputs-before.json').write_text(json.dumps(before, indent=2), encoding='utf-8')
home = HERE / 'candidate' / 'home'
home.mkdir()
environment = {key: os.environ[key] for key in ('SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT') if key in os.environ}
environment.update(PATH=str(Q.parent) + ';' + str(Path(environment['SYSTEMROOT']) / 'System32'),
                   HOME=str(home), USERPROFILE=str(home), APPDATA=str(home), LOCALAPPDATA=str(home),
                   TEMP=str(home), TMP=str(home), PYTHONDONTWRITEBYTECODE='1')
wheels = HERE / 'candidate' / 'wheels'
with (HERE / 'candidate' / 'build.log').open('w', encoding='utf-8') as log:
    process = subprocess.Popen([str(Q), '-I', '-m', 'build', '--wheel', '--no-isolation',
        '--outdir', str(wheels), str(snapshot)], cwd=home, env=environment,
        stdout=log, stderr=subprocess.STDOUT)
    print(json.dumps({'pid': process.pid, 'stage': 'build'}), flush=True)
    code = process.wait()
assert code == 0, code
wheel, = wheels.glob('*.whl')
with zipfile.ZipFile(wheel) as archive:
    files = {name: hashlib.sha256(archive.read(name)).hexdigest() for name in archive.namelist()
             if name.startswith('nexus_connector_core/') and not name.endswith('/')}
    for name, digest in files.items():
        assert digest == hashlib.sha256((ROOT / 'src' / name).read_bytes()).hexdigest(), name
assert before == inputs(ROOT)
report = {'wheel': str(wheel), 'wheel_sha256': hashlib.sha256(wheel.read_bytes()).hexdigest(),
          'package_file_count': len(files), 'package_files': files, 'source_equals_wheel': True,
          'inputs_unchanged': before == inputs(ROOT), 'build_exit_code': code,
          'scope': 'Candidate only; live campaign packages untouched'}
(HERE / 'candidate' / 'package-proof.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps({key: value for key, value in report.items() if key != 'package_files'}), flush=True)
