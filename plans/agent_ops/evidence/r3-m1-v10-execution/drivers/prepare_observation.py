from pathlib import Path
import hashlib,json
source=Path('D:/Projetos/Techridy/okto_labs_okto_nexus/plans/agent_ops/evidence/r3-m1-v9-execution/drivers')
target=Path(__file__).parent
pins={}
for name in ('m1_v9_nexus_observation.py','m1_v9_confirm_cleanup.py'):
    raw=(source/name).read_text(encoding='utf-8')
    raw=raw.replace('m1-v9-preparation-t4xaqhca','m1-v10-bundle-pscf18t5').replace('proposal-v9.json','proposal-v10.json')
    raw=raw.replace('9a7004d1670076fd516311932bb894fbd55e47e2625fb6b3dfd89dc66caed279','90c2ed2ca18e7fd86380c614e516a5f8975af2a2052b56a3609004be4814405a').replace('54913','56237')
    assert 'v9' not in raw
    path=target/name.replace('v9','v10')
    with path.open('x',encoding='utf-8',newline='\n') as stream:stream.write(raw)
    pins[path.name]=hashlib.sha256(path.read_bytes()).hexdigest()
(target/'observation-driver-pins.json').write_text(json.dumps(pins,indent=2)+'\n',encoding='utf-8')
print(json.dumps(pins))
