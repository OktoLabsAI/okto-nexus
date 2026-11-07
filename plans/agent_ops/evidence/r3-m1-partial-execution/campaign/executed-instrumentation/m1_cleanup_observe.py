from pathlib import Path
import json,sys,time
sys.path.insert(0,'C:/Users/jpamb/AppData/Local/Temp')
from m1_real_lifecycle import ROOT,C
from okto_nexus.adapters.inbound.cli.service import resolve_local_service
service=resolve_local_service(C['service_selection_args'])
value=service.inspect()
# The installed service inspection is an intentional public status contract.
(ROOT/'public/cleanup-service-status.json').write_text(json.dumps({'observed_at':time.time(),'status':value,'new_lifecycle_mutations':0},indent=2))
original=json.loads((ROOT/'private/nexus-stop.stdout').read_text())
(ROOT/'public/stop-timeout-receipt.json').write_text(json.dumps(original,indent=2))
data=json.loads((ROOT/'private/controller.json').read_text())
collector=data['collector']['state']
report={'known_observed_minimum':45843,'private_faults':data['faults'],'admissions':len(data['requests']),
        'setup':{k:{field:r['monitor'].get(field) for field in ('high_water','cursor','started','terminal','usage_seen','caught_up','result_stage','close_stage','owned_slot_released')}
                 for k,r in data['requests'].items() if r['kind']=='setup'},
        'streams':{k:{field:s.get(field) for field in ('scope','epoch','cursor','watermark','gap','page_seen','retired','native_thread_id')} for k,s in collector['streams'].items()},
        'turns':{k:{field:t.get(field) for field in ('operation_id','stream','started','terminal','usage_seen','high_water','turn_id','state')} for k,t in collector['turns'].items()},
        'threads':{k:{field:t.get(field) for field in ('high_water','baseline_total','baseline_basis','native_thread_id')} for k,t in collector['threads'].items()},
        'note':'Metadata projections only. These observations are not billed/final usage. No private frames copied.'}
(ROOT/'public/final-accounting-coverage.json').write_text(json.dumps(report,indent=2))
print(json.dumps({'status':value,'coverage':report}))
