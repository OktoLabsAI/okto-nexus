from pathlib import Path
import hashlib,json

HERE=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(name,value):
    with (HERE/name).open('x',encoding='utf-8') as f:json.dump(value,f,indent=2)
capture=json.loads((HERE/'local-diagnostic.json').read_bytes())
assert capture['status']=='READ_ONLY_CAPTURED' and not capture['truncated']
allowed={'provider','event_id','version','record_id','utc','transition'}
manifest={(x['event_id'],x['version']):x for x in capture['manifest']}
for row in capture['events']:
    assert set(row)==allowed
    assert row['provider']=='Microsoft-Windows-Kernel-Power'
    assert manifest[row['event_id'],row['version']]['transition']==row['transition']
ancestor=Path('C:/Users/jpamb/AppData/Local/Temp/r3-windows-attempt-bound-cqbln3b4')
pins={'plan-template.json':'2c14d1ceec1c69d7d89dbb39ffdb4b75bcea2a751f7477c7afc5fb896df5036b',
      'attempt_contract.py':'c832c9e09bcf1b3e1683da75be5ebe104b33ee92f837d9799d0c78bebf214b7a',
      'automation_contract.py':'98ff23b98e32f679834fb34227a0df7196f776bf95a798baf92d41588bc1791c'}
for name,expected in pins.items():assert sha(ancestor/name)==expected
write('qualification.json',{'status':'OFFLINE_QUALIFIED_UNSELECTED','tests':{'unique_cases':3,'passed':3,'failed':0,
  'tool_observation':'8a5014','seconds':0.229,'raw_test_log_not_retained':True},
  'read_only_capture':{'tool_observation':'285f26','status':capture['status'],'events':len(capture['events']),
    'truncated':False,'sha256':sha(HERE/'local-diagnostic.json'),'runtime_projection_allowlist_verified':True},
  'ancestor_pins':[{'path':str(ancestor/n),'sha256':s} for n,s in pins.items()],
  'event_generated':False,'task_published':False,'services_controlled':False,'provider_calls':0,
  'scenario_acceptance':'NOT_RUN','old_receipts_unchanged':True,
  'scope':'OS-recorded transition only; no deep-state residency or API-causation claim'})
names=['capture.ps1','transition_proof.py','test_transition_proof.py','REVIEW.md','seal.py','local-diagnostic.json','qualification.json']
write('public-allowlist.json',{'files':[{'path':n,'sha256':sha(HERE/n),'bytes':(HERE/n).stat().st_size} for n in names]})
print(json.dumps({n:sha(HERE/n) for n in ('qualification.json','public-allowlist.json','capture.ps1','transition_proof.py')}))
