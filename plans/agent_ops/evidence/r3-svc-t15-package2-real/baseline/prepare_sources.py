"""Extract previously reviewed helpers into this new candidate only."""
from pathlib import Path
import ast,hashlib,json
ROOT=Path(__file__).resolve().parent
old=Path('C:/Users/jpamb/AppData/Local/Temp/r3-svc-t15-env-zrrzik82/resume02-v2/run_case.py')
t19=Path('C:/Users/jpamb/AppData/Local/Temp/r3-native-t19-t20-v2-fk9g74yv/run.py')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert sha(old)=='e12f28399d88e57ec5c91a5da1fa7d612fd1b1ff3f5e245a21f6605075649937'
assert sha(t19)=='b72d525e09ae8e968eaf09481851c5582d9f25135c234f3ead7696d64746eff6'
def extract(path,names):
    text=path.read_text(encoding='utf-8');tree=ast.parse(text)
    nodes={n.name:ast.get_source_segment(text,n) for n in tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
    return '\n\n\n'.join(nodes[name] for name in names)+'\n'
connection='''"""Pinned canonical connection helpers; no actions at import."""
from pathlib import Path
import asyncio,copy,hashlib,json,os,secrets,sqlite3,time
from urllib.parse import quote
BASE=Path(__file__).resolve().parent
ROOT=BASE/'case'
PUBLIC=BASE/'public'
PRIVATE=BASE/'private'
PROFILE='svc-t15-final-terminal-only'
VARIABLE='SVC_T15_ONLY_CLI_KEY'
REFERENCE='provider:'+VARIABLE
PREFIX='/api/v1/runtime-management'
CONFIG='cli_auth_credentials_store = "file"\\n'
'''
connection += extract(old,['Refused','require','sha','save','ObservedHTTP','environment','python_argv','probe',
    'selected_request','validate_test','retained_data','journal_proof','setup_case','matching_candidate','observe_candidate'])
connection=connection.replace('svc-t15-terminal-only-01','svc-t15-final-terminal-only-01')
with (ROOT/'connection_case.py').open('x',encoding='utf-8') as f:f.write(connection)
cohort='''"""Retained query-only lifecycle cohort, extracted from qualified T19 helpers."""
from pathlib import Path
import time,xml.etree.ElementTree as ET
import runtime_support as support
from runtime_support import PUBLIC,require,sha,save
'''
cohort+=extract(t19,['native_stamp','native_contract','cycle_projection','validate_cycle','capture_cycle',
    'wait_exits','wait_native_inactive','failure_handoff'])
with (ROOT/'cohort.py').open('x',encoding='utf-8') as f:f.write(cohort)
support=(ROOT/'runtime_support.py').read_text()
support=support.replace('can_terminate=True','can_terminate=False')
support=support.replace('self.can_terminate = can_terminate',"require(can_terminate is False, 'TERMINATION_RIGHT_REFUSED')\n        self.can_terminate = False")
support=support.replace('0x1000 | 0x100000 | (0x0001 if can_terminate else 0)','0x1000 | 0x100000')
(ROOT/'runtime_support.py').write_text(support,encoding='utf-8',newline='\n')
with (ROOT/'source-ancestry.json').open('x',encoding='utf-8') as f:
    json.dump({'prior_connection':{'path':str(old),'sha256':sha(old)},'cohort':{'path':str(t19),'sha256':sha(t19)},
        'runtime_support_delta':'Query/synchronize only; terminate access refused.'},f,indent=2)
