"""Benign source handshake probe. Never calls runtime/bootstrap or a provider."""
import json
import os
from pathlib import Path
import sys
import time

sys.path[:0] = ['D:/Projetos/Techridy/okto_labs_okto_nexus/src',
                'D:/Projetos/Techridy/okto-nexus-connector-core/src']
from okto_nexus.adapters.outbound.service_manager import supervision as s
from okto_nexus.adapters.outbound.service_manager.context import read_json

home = Path(sys.argv[1])
meta = read_json(home/'probe.json')
class Installation:
    instance_id = meta['instance_id']
    def receipt(self): return {'token': meta['token']}
    def control(self, receipt): return read_json(home/'service-control.json')

identity = {'pid': os.getpid(), 'birth': s.own_birth(), 'parent_pid': os.getppid()}
with (home/'probe-runtime-identity.json').open('x', encoding='utf-8') as out:
    json.dump(identity, out)
if meta['mode'] == 'previous-parent-exited':
    time.sleep(1)  # Probe observer retains identity before the cooperative refusal.
code = 0
try:
    allowed = s.join_parent(home, home/'never-created.db', Installation(), meta['token'],
                           meta['cycle_id'], meta['nonce'])
    if allowed:
        acknowledged = read_json(home/'service-supervisor.json')['child_acknowledged']
        assert acknowledged is True
        with (home/'bootstrap-marker.json').open('x', encoding='utf-8') as out:
            json.dump({'pid':os.getpid(),'acknowledged_before_marker':acknowledged}, out)
    result = {'allowed':allowed,'code':0}
except Exception as error:
    code = 2
    result = {'allowed':False,'code':2,'reason':getattr(error,'code',type(error).__name__)}
with (home/'child-result.json').open('x',encoding='utf-8') as out: json.dump(result,out)
raise SystemExit(code)
