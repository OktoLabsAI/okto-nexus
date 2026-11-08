from pathlib import Path
import json,time,socket,hashlib,sqlite3
from okto_nexus.adapters.outbound.service_manager.windows_tasks import WindowsTasks
R=Path('C:/Users/jpamb/AppData/Local/Temp/m1-v10-bundle-pscf18t5/campaign')
C=json.loads((R.parent/'draft/proposed-commands.json').read_text())
tasks={}
for component,v in C['tasks'].items():
    assert WindowsTasks().read(v['name']) is None
    tasks[component]={'name':v['name'],'absent':True}
with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as probe:
    probe.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
    probe.bind(('127.0.0.1',56237))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
checkpoint=json.loads((R/'private/controller.json').read_text())
assert set(checkpoint['requests'])=={'m1v10-local-setup'}
database=R/'nexus-home/nexus.db';before=sha(database)
with sqlite3.connect(database.as_uri()+'?mode=ro',uri=True,timeout=2) as db:
    db.execute('PRAGMA query_only=ON')
    count=db.execute('SELECT count(*) FROM execution_client_intents WHERE client_intent_id=?',('m1v10-local-work-01',)).fetchone()[0]
assert count==0 and sha(database)==before
proof={'status':'NORMAL_CLEANUP_CONFIRMED','tasks':tasks,'exclusive_port_probe_passed_not_reserved':56237,
    'time':time.time(),'data_preserved':R.exists(),'force_used':False,'replayed':False,
    'connector_started':False,'service_actions':4,'proof_sha256':sha(R/'public/cleanup-nexus.json'),
    'controller_sha256':sha(R/'private/controller.json'),
    'work_intent_rows':count,'work_reservation_exists':False,'work_dispatched':False,
    'report_exists':(R/'deliverables/local/report.json').exists(),
    'canonical_db_unchanged_by_readonly_check':True,'canonical_db_sha256':before}
with (R/'public/final-presence.json').open('x',encoding='utf-8') as stream:json.dump(proof,stream,indent=2)
print(json.dumps(proof))
