import hashlib
import importlib
import importlib.metadata
import json
import platform
from pathlib import Path
import sys
import zipfile

own=Path(__file__).resolve().parent
report={'python':sys.version,'executable':sys.executable,'os':platform.platform(),'cwd':str(Path.cwd()),
        'isolated':sys.flags.isolated,'sys_path':sys.path,'packages':{},'assets':{},'provider_qualified':False}
for package,module in (('okto-nexus','okto_nexus'),('okto-nexus-connector','okto_nexus_connector'),('okto-nexus-connector-core','nexus_connector_core'),('pytest','pytest')):
    loaded=importlib.import_module(module)
    origin=str(Path(loaded.__file__).resolve())
    assert 'site-packages' in origin,origin
    report['packages'][package]={'version':importlib.metadata.version(package),'origin':origin}
build=sys.argv[1] if len(sys.argv)>1 else 'nexus'
wheel=next((own/build).glob('*.whl'))
with zipfile.ZipFile(wheel) as archive:
    for name in archive.namelist():
        if '/static/' in name and not name.endswith('/'):
            report['assets'][name]=hashlib.sha256(archive.read(name)).hexdigest()
expected=sys.argv[2] if len(sys.argv)>2 else 'index-CIRJLndB.js'
assert any(name.endswith('/assets/'+expected) for name in report['assets'])
assert any(name.endswith('/assets/index-CXFy-VnM.css') for name in report['assets'])
assert report['packages']['okto-nexus']['version']=='0.3.5'
assert report['packages']['okto-nexus-connector']['version']=='0.0.13'
assert report['packages']['okto-nexus-connector-core']['version']=='0.0.14'
(own/('installed-environment.json' if build=='nexus' else 'installed-environment-final.json')).write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
