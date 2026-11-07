"""Offline import/byte proof, plus exactly two optional Task Scheduler reads."""
import argparse
import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument('--imports-only', action='store_true')
parser.add_argument('--output', required=True)
args = parser.parse_args()

import okto_nexus
import okto_nexus_connector
import nexus_connector_core
from okto_nexus.service_environment import snapshot as nexus_snapshot
from okto_nexus_connector.service_environment import snapshot as connector_snapshot


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def inventory(folder):
    return {path.relative_to(folder).as_posix(): sha(path.read_bytes()) for path in sorted(folder.rglob('*'))
        if path.is_file() and '__pycache__' not in path.parts and path.suffix not in ('.pyc', '.pyo')}


packages = {}
for module, distribution, repo in (
    (okto_nexus, 'okto-nexus', Path('D:/Projetos/Techridy/okto_labs_okto_nexus')),
    (okto_nexus_connector, 'okto-nexus-connector', Path('D:/Projetos/Techridy/okto-nexus-connector')),
    (nexus_connector_core, 'okto-nexus-connector-core', Path('D:/Projetos/Techridy/okto-nexus-connector-core'))):
    package = module.__name__
    installed = Path(module.__file__).resolve().parent
    assert installed.is_relative_to(ROOT / 'venv/Lib/site-packages')
    wheel, = (ROOT / 'wheels').glob(distribution.replace('-', '_') + '-*.whl')
    with zipfile.ZipFile(wheel) as archive:
        wheel_files = {name[len(package) + 1:]: sha(archive.read(name)) for name in archive.namelist()
            if name.startswith(package + '/') and not name.endswith('/')}
    current = inventory(repo / 'src' / package)
    assert current == inventory(installed) == wheel_files, package + ': current source/wheel/install mismatch'
    dist = metadata.distribution(distribution)
    direct = dist.read_text('direct_url.json')
    assert direct is None or not json.loads(direct).get('dir_info', {}).get('editable')
    packages[distribution] = dict(version=dist.version, import_path=str(installed), wheel=str(wheel),
        wheel_sha256=sha(wheel.read_bytes()), file_count=len(current), files=current,
        current_source=str(repo), exact_source_wheel_install=True)

result = dict(status='READ_ONLY_PREPARATION', executable=sys.executable,
    executable_sha256=sha(Path(sys.executable).read_bytes()), sys_prefix=sys.prefix,
    user_site_enabled=False, packages=packages,
    canonical_environment_snapshots=dict(nexus=nexus_snapshot(), connector=connector_snapshot()))
if not args.imports_only:
    from okto_nexus.adapters.outbound.service_manager.installation import ServerInstallation
    from okto_nexus_connector.platform.user_service import UserService
    home, state = ROOT / 'campaign/nexus', ROOT / 'campaign/connector'
    nexus = ServerInstallation(home, home / 'nexus.db')
    connector = UserService(state)
    observations = {}
    for name, service in [('nexus', nexus), ('connector', connector)]:
        observed = service.tasks.read(service.name)
        observations[name] = dict(task_name=service.name, instance_id=service.instance_id,
            exists=observed is not None, native_api_called='WindowsTasks.read only')
        assert observed is None, 'Target task exists; no action was taken and no task content exported.'
    result['task_observations'] = observations
    result['campaign_dirs_empty'] = all(not any(path.iterdir()) for path in (home, state))
    assert result['campaign_dirs_empty']
with (ROOT / args.output).open('x', encoding='utf-8') as stream:
    json.dump(result, stream, indent=2)
