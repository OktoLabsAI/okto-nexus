"""Three exact wheels into own Linux venv only; no global/user pip."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('qc28_bootstrap', HERE / 'bootstrap.py')
boot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(boot)
root = boot.ROOT
assert (root / 'bootstrap-ready.json').exists()
managed = list((root / 'python').glob('cpython-3.13.1-*/bin/python3.13'))
assert len(managed) == 1
boot.run('managed-python-version', [str(managed[0]), '-I', '-B', '-c', 'import sys;assert sys.version_info[:3]==(3,13,1);print(sys.version)'])
boot.run('venv', [str(root / 'uv'), 'venv', '--python', str(managed[0]), '--no-config', str(root / 'venv')])
wheels = root / 'wheels'
wheels.mkdir(exist_ok=True)
sources = [
    ('/mnt/c/Users/jpamb/AppData/Local/Temp/nexus-qc-r1-package-t24_dnfc/artifacts/okto_nexus-0.3.6-py3-none-any.whl', 'a36e448c80a8190c7e8c92d81ea5a251c4bdf7e370eca0f0b395a5ad29e36cc6'),
    ('/mnt/d/Projetos/Techridy/okto_labs_okto_nexus/vendor/wheels/okto_nexus_connector_core-0.0.14-py3-none-any.whl', 'ea1797805279667a5b39fdb6e9e6185ed8dcb958a1c7f98e91651e841754dca5'),
    ('/mnt/d/Projetos/Techridy/okto_labs_okto_nexus/vendor/ci/okto_nexus_connector-0.0.13-py3-none-any.whl', '4095484f14110b845b3481941330810f3de1d8fadf9051de0b724cb824177b90'),
]
pins = {}
for source, expected in sources:
    source = Path(source)
    assert hashlib.sha256(source.read_bytes()).hexdigest() == expected
    target = wheels / source.name
    shutil.copyfile(source, target)
    assert hashlib.sha256(target.read_bytes()).hexdigest() == expected
    pins[source.name] = expected
boot.write('wheel-pins.json', pins)
python = root / 'venv/bin/python'
boot.run('install', [str(root / 'uv'), 'pip', 'install', '--python', str(python), '--no-config',
    '--cache-dir', str(root / 'cache'), '--default-index', 'https://pypi.org/simple',
    str(wheels / Path(sources[0][0]).name) + '[serve-lite,dev]',
    str(wheels / Path(sources[1][0]).name), str(wheels / Path(sources[2][0]).name)])
boot.run('pip-check', [str(root / 'uv'), 'pip', 'check', '--python', str(python), '--no-config'])
boot.write('package-ready.json', dict(status='OWN_POSIX_PREFIX_READY', python=str(python), wheel_pins=pins))
