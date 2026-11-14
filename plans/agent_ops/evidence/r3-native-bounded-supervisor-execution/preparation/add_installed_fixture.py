from pathlib import Path
import hashlib,json,shutil,subprocess
ROOT=Path(__file__).resolve().parent
commit='6714d69563f86e965b7551239a09367982eadbca'
source='tests/test_service_start.py'
data=subprocess.run([shutil.which('git'),'-C','D:/Projetos/Techridy/okto_labs_okto_nexus','show',commit+':'+source],capture_output=True,check=True).stdout
path=ROOT/'installed-tests/test_service_start.py'
with path.open('xb') as out:out.write(data)
with (ROOT/'installed-fixture-added.json').open('x',encoding='utf-8') as out:
    json.dump({'source_path':source,'commit':commit,'sha256':hashlib.sha256(data).hexdigest(),
        'reason':'Initial collection stopped before tests: imported fixture test_service_start missing; original XML retained.'},out,indent=2)
