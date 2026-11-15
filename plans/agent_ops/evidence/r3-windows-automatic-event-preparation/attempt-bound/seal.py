from pathlib import Path
import ast,hashlib,json
HERE=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(n,v):
    with (HERE/n).open('x',encoding='utf-8') as f:json.dump(v,f,indent=2,sort_keys=True)
for p in HERE.glob('*.py'):ast.parse(p.read_text(encoding='utf-8'))
test=json.loads((HERE/'test-result.json').read_bytes());assert (test['tests'],test['failures'],test['errors'])==(6,0,0)
ancestry=json.loads((HERE/'ancestry.json').read_bytes())
assert all(sha(Path(ancestry['original_root'])/name)==value for name,value in ancestry['original_sources'].items())
plan=json.loads((HERE/'plan-template.json').read_bytes());assert plan['selected_event'] is None and not plan['reviewed_for_execution']
assert not (HERE/'selections').exists()
for pin in plan['read_only_dependencies']:assert sha(Path(pin['path']))==pin['sha256']
save('qualification.json',{'status':'OFFLINE_ATTEMPT_BOUND_SUCCESSOR_QUALIFIED_UNSELECTED','test_result':test,'test_tool':'a3edc5',
    'plan_sha256':sha(HERE/'plan-template.json'),'runtime_files':{p.name:sha(p) for p in HERE.glob('*.py')},
    'originals_byte_identical':True,'effects_executed':0,'native_calls_tested_live':False,'task_published':False,
    'event_selected':False,'service_provider_or_login_effects':0})
paths=sorted(p for p in HERE.iterdir() if p.is_file() and p.name!='public-allowlist.json')
save('public-allowlist.json',{'files':[{'path':str(p),'sha256':sha(p),'bytes':p.stat().st_size} for p in paths]})
print(json.dumps({n:sha(HERE/n) for n in ('plan-template.json','qualification.json','public-allowlist.json')}))
