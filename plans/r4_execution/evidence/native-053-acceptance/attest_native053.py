from pathlib import Path
import hashlib
import importlib.util
import importlib.metadata
import json
import platform
import sys
import zipfile

temp = Path('C:/Users/jpamb/AppData/Local/Temp')
artifacts = {
    'okto_nexus':temp/'okto-nexus-r4-053-dist/okto_nexus-0.2.0-py3-none-any.whl',
    'nexus_connector_core':temp/'okto-core-r4-053-dist/nexus_connector_core-0.2.53.dev0-py3-none-any.whl',
    'okto_nexus_connector':temp/'okto-connector-r4-053-dist/okto_nexus_connector-0.5.0.dev0-py3-none-any.whl',
}
local_only = '--local-only' in sys.argv
report = dict(python=sys.version, executable=sys.executable, platform=platform.platform(),
              isolated=sys.flags.isolated, local_only=local_only, packages={})
for module, wheel in artifacts.items():
    spec = importlib.util.find_spec(module)
    if local_only and module == 'okto_nexus_connector':
        assert spec is None
        report['connector_installed'] = False
        continue
    assert spec is not None and spec.origin
    folder = Path(spec.origin).parent
    verified = {}
    with zipfile.ZipFile(wheel) as archive:
        for name in archive.namelist():
            if not name.startswith(module+'/') or name.endswith('/'):
                continue
            installed = folder/Path(name).relative_to(module)
            assert installed.is_file() and installed.read_bytes() == archive.read(name), name
            verified[name] = hashlib.sha256(installed.read_bytes()).hexdigest()
    report['packages'][module] = dict(path=str(folder), wheel=str(wheel),
        wheel_sha256=hashlib.sha256(wheel.read_bytes()).hexdigest(), installed_files=verified)
report['installed_distributions'] = sorted(
    (d.metadata['Name'], d.version) for d in importlib.metadata.distributions())
Path(sys.argv[1]).write_text(json.dumps(report, indent=2)+'\n')
print('Verified package bytes; local_only='+str(local_only))
