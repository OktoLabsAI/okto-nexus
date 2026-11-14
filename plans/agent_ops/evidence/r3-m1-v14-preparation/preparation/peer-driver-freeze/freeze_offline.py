"""Freeze public offline artifacts; never imports a service or campaign runtime."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import shutil
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parent
BASE=Path('C:/Users/jpamb/AppData/Local/Temp/m1-v12-bundle-bldo9qy7/successor13')
DRAFT=BASE.parent/'successor14/draft'
QUAL=ROOT/'qualification';QUAL.mkdir(exist_ok=True)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,v):p.write_text(json.dumps(v,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
def pin(p):return {'path':str(p),'sha256':sha(p),'bytes':p.stat().st_size}
names={'root_driver_adopt_local':'adopt_local.py','root_driver_authorize_local':'authorize_local.py',
    'root_driver_operator_bootstrap':'operator_bootstrap.py','root_driver_common':'driver_common.py',
    'root_driver_invoke':'invoke.py','root_driver_prepare_observation':'prepare_observation.py',
    'root_driver_observation':'m1_v14_observation.py','root_driver_confirm_cleanup':'m1_v14_confirm_cleanup.py',
    'root_driver_confirm_final_presence':'confirm_final_presence.py','root_driver_close_campaign':'close_campaign.py'}
for p in ROOT.glob('*.py'):compile(p.read_text(encoding='utf-8'),str(p),'exec')
derivation=[]
for key,name in names.items():
    old=BASE/'root-drivers'/name.replace('m1_v14_','m1_v13_')
    before=old.read_text(encoding='utf-8')
    mechanical=before.replace('m1_v13_','m1_v14_').replace('successor13','successor14')
    derivation.append({'module':key,'predecessor':pin(old),'current':pin(ROOT/name),
        'semantic_delta_beyond_import_revision':mechanical!=(ROOT/name).read_text(encoding='utf-8')})
save(QUAL/'runtime-pins.json',{'format':'m1-v14-root-driver-runtime-freeze',
    'status':'FROZEN_QUALIFIED_OFFLINE','files':{k:pin(ROOT/v) for k,v in names.items()}})
for source,target in [('delta-initial.xml','antecedent-61pass-2fixturefails.xml'),
    ('delta-final.xml','final.xml'),('delta-done-checkpoint.xml','prior-done-checkpoint.xml')]:
    shutil.copyfile(ROOT/source,QUAL/target)
def counts(p):
    t=ET.parse(p).getroot()
    suites=[t] if t.tag=='testsuite' else list(t)
    return {k:sum(int(s.get(k,0)) for s in suites) for k in ('tests','failures','errors','skipped')}
assert counts(QUAL/'final.xml')=={'tests':63,'failures':0,'errors':0,'skipped':0}
assert counts(QUAL/'prior-done-checkpoint.xml')=={'tests':1,'failures':0,'errors':0,'skipped':0}
assert counts(QUAL/'antecedent-61pass-2fixturefails.xml')=={'tests':63,'failures':2,'errors':0,'skipped':0}
installed=BASE.parent/'draft/installation/venv/Lib/site-packages'
origins=[installed/'okto_nexus/adapters/inbound/cli/work.py',
    installed/'okto_nexus/application/terminal_authorization.py',
    installed/'okto_nexus/application/terminal_work.py',
    installed/'okto_nexus/application/terminal_connection.py',
    DRAFT/'controller/cli_flow.py',DRAFT/'controller/token_collector.py',DRAFT/'publication.py']
save(QUAL/'qualification.json',{'format':'m1-v14-root-driver-offline-qualification','status':'PASS_DELTA',
    'generated_at':datetime.now(timezone.utc).isoformat(),
    'runtime_manifest_sha256':sha(QUAL/'runtime-pins.json'),
    'pytest':{'final':dict(counts(QUAL/'final.xml'),artifact=pin(QUAL/'final.xml')),
        'additional_prior_done':dict(counts(QUAL/'prior-done-checkpoint.xml'),artifact=pin(QUAL/'prior-done-checkpoint.xml')),
        'total_distinct_final_cases':64,'command_prefix':'rtk proxy C:/Users/jpamb/AppData/Local/Temp/m1-v12-bundle-bldo9qy7/draft/installation/venv/Scripts/python.exe -I -B -X utf8',
        'runners':['qualify_delta.py','qualify_done_checkpoint.py'],
        'scope':'Installed parser/handlers against synthetic HTTP and topology; no effects. Delta only, not an assertion that all inherited119 were rerun.'},
    'antecedents':[{'artifact':pin(QUAL/'antecedent-61pass-2fixturefails.xml'),
        'counts':'61PASS/2fixtureFAIL','cause':'The no-effects Popen replacement ran before Windows asyncio imported its Popen subclass; preimport asyncio before fixture fixes the two import failures. No product/CLI entered those failing cases.'}],
    'prior_qualification':pin(BASE/'public-artifacts/peer-driver-freeze/qualification/qualification.json'),
    'derivation':derivation,'origins':[pin(p) for p in origins],
    'compile':'PASS: every candidate Python source compiled in memory; no pyc writes',
    'ruff':'PASS: E9,F63,F7,F82 on candidate before final test-only prior-done parameter',
    'scope':['Fresh revision14 receipt and carry9/134199/new4/cumulative13 identities',
        'GET-only adoption with exact old checkpoint bytes snapshot before new controller',
        'New local request IDs separate from reused m1v12-local profile',
        'Complete two-grant history revision/expiry/max/actions and monotonic used counters',
        'Unique available grant balance>=3 reused; expired history requires exact root review and max3 replacement',
        '630s admission window for one600s turn plus30s margin; canonical server revalidates every admission',
        'Declared publication parent included before hermetic import; no inherited sibling path required',
        'Post-authorization checkpoint hash exported for first new-session scope validation'],
    'limitations':['No real receipt, controller, service, provider, login or campaign was executed.',
        'Prior119-case v13 qualification reused for unchanged inherited behavior, not repeated.',
        'Work freshness1s/poll600ms/read250ms and model600s limits are composed by preparer, not changed by these drivers.',
        'Authorization maintenance retains120s separate from600s work deadline.',
        'Root source review and final campaign composition/authorization remain separate from offline qualification.']})
files=[ROOT/name for name in names.values()]
files += list(ROOT.glob('test_*.py'))+[ROOT/'qualify_delta.py',ROOT/'qualify_done_checkpoint.py',ROOT/'freeze_offline.py']
files += [QUAL/n for n in ('runtime-pins.json','qualification.json','final.xml','prior-done-checkpoint.xml','antecedent-61pass-2fixturefails.xml')]
save(ROOT/'public-allowlist.json',{'source_root':str(ROOT),'files':[
    {'path':p.relative_to(ROOT).as_posix(),'sha256':sha(p),'bytes':p.stat().st_size} for p in files]})
print(json.dumps({n:sha(ROOT/n) for n in ('qualification/runtime-pins.json','qualification/qualification.json','public-allowlist.json')}))
