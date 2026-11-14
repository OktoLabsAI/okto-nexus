"""Copy exact committed test bytes for offline installed qualification."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess

ROOT=Path(__file__).resolve().parent
target=ROOT/'installed-tests';target.mkdir()
git=shutil.which('git');assert git
selections={
 'core':('D:/Projetos/Techridy/okto-nexus-connector-core','7810f3b9bd2576bca5ccc8286a4c661789bf73a4',['tests/test_user_service_supervision.py','tests/test_user_service_definition.py']),
 'nexus':('D:/Projetos/Techridy/okto_labs_okto_nexus','6714d69563f86e965b7551239a09367982eadbca',['tests/test_service_supervisor.py','tests/test_user_service_installation.py']),
 'connector':('D:/Projetos/Techridy/okto-nexus-connector','e612ff852cf22264c52cc9d083548d6100a60efa',['tests/unit/test_bounded_service_supervisor.py']),
}
pins=[]
for product,(repo,commit,paths) in selections.items():
    for source in paths:
        data=subprocess.run([git,'-C',repo,'show',commit+':'+source],capture_output=True,check=True).stdout
        path=target/Path(source).name
        with path.open('xb') as out:out.write(data)
        pins.append({'path':path.name,'sha256':hashlib.sha256(data).hexdigest(),'commit':commit,'source_path':source})
with (ROOT/'installed-test-pins.json').open('x',encoding='utf-8') as out:json.dump(pins,out,indent=2)
