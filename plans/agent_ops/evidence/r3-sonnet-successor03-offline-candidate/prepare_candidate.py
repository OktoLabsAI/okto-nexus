from pathlib import Path
import hashlib,json,shutil
HERE=Path(__file__).resolve().parent
U=Path('C:/Users/jpamb/AppData/Local/Temp/m1-sonnet-remote-candidate-2c_4af0t/successor02')
R=Path('C:/Users/jpamb/AppData/Local/Temp/sonnet-canonical-recovery-proposal-7oq808_t')
def ref(p):
    p=Path(p);return {'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}
def write(name,value):
    with (HERE/name).open('x',encoding='utf-8') as f:json.dump(value,f,indent=2);f.write('\n')
def change(text,old,new):
    assert old in text,old
    return text.replace(old,new)
names=('work_context.py','work-entry.py','remote_work.py','observe_active.py','activecontrol.py','request_context.py','reused_observation.py','sonnet_usage.py')
for name in names:shutil.copyfile(U/name,HERE/name)
s=(HERE/'sonnet_usage.py').read_text()
s=change(s,"require(0<preventive<limit==200000 and 1<=max_requests<=3,'POLICY_INVALID')","require((limit,preventive,max_requests) in ((200000,150000,3),(200000,180000,3),(500000,480000,4)),'POLICY_INVALID')")
s=change(s,'def __init__(self,*,preventive=150000):','def __init__(self,*,preventive=150000,limit=200000,max_requests=3):')
s=change(s,"require(0<preventive<200000,'POLICY_INVALID')","require((limit,preventive,max_requests) in ((200000,150000,3),(200000,180000,3),(500000,480000,4)),'POLICY_INVALID')")
s=change(s,'self.preventive=preventive;self.sessions={}','self.preventive=preventive;self.limit=limit;self.max_requests=max_requests;self.sessions={}')
s=s.replace('len(self.sessions)<3','len(self.sessions)<self.max_requests').replace('len(x.reserved) for x in self.sessions.values())<3','len(x.reserved) for x in self.sessions.values())<self.max_requests')
s=s.replace("'limit':200000}","'limit':self.limit}")
s=change(s,"body={'format':'sonnet-campaign-usage-v1','preventive':budget.preventive,'sessions':sessions}","body={'format':'sonnet-campaign-usage-v2','preventive':budget.preventive,'limit':budget.limit,'max_requests':budget.max_requests,'sessions':sessions}")
s=change(s,"body.get('format')=='sonnet-campaign-usage-v1'","body.get('format') in ('sonnet-campaign-usage-v1','sonnet-campaign-usage-v2')")
s=change(s,"b=CampaignBudget(preventive=body['preventive'])","b=CampaignBudget(preventive=body['preventive'],limit=body.get('limit',200000),max_requests=body.get('max_requests',3))")
s=s.replace('len(b.sessions)<3','len(b.sessions)<b.max_requests')
(HERE/'sonnet_usage.py').write_text(s,encoding='utf-8')
s=(HERE/'remote_work.py').read_text().replace('Ledger(scope,preventive=budget.preventive)','Ledger(scope,limit=budget.limit,preventive=budget.preventive,max_requests=budget.max_requests)')
(HERE/'remote_work.py').write_text(s,encoding='utf-8')
s=(HERE/'work_context.py').read_text()
s=s.replace("'m1-sonnet-remote-useful-03'","'m1-sonnet-remote-useful-05'").replace("'m1-sonnet-remote-continuation-04'","'m1-sonnet-remote-continuation-06'")
s=change(s,"self.P=read_json(path);self.plan_sha256=expected","self.P=read_json(path);self.plan_sha256=expected\n        from successor_policy import authorize_plan\n        authorize_plan(self.P)")
s=s.replace("{'limit':200000,'preventive':180000,'initial_reserve':50000,'next_input_multiplier':2,'next_output_margin':32000}","{'limit':500000,'preventive':480000,'initial_reserve':50000,'next_input_multiplier':2,'next_output_margin':32000}")
start=s.index('        from sonnet_usage import restore_budget,checkpoint_budget',s.index('    def validate_budget'))
end=s.index('\n    def prepare(self):',start)
s=s[:start]+"        from successor_policy import validate_history\n        validate_history(budget,read_json(pin(self.P['budget_seed'])))\n"+s[end:]
s=s.replace("'carried_observed_tokens':36306,'carried_reservations':1,'preventive':180000,'limit':200000","'carried_observed_tokens':144004,'carried_reservations':2,'preventive':480000,'limit':500000")
(HERE/'work_context.py').write_text(s,encoding='utf-8')
shutil.copyfile(U/'paid-work/private/sonnet-budget.json',HERE/'historical-budget.json')
write('candidate.json',{'status':'OFFLINE_CANDIDATE_AUTHORIZATION_AND_FRESH_PACKAGE_COHORTS_PENDING','proposal':ref(R/'remaining-sonnet-budget-proposal.json'),'original_plan':ref(U/'work-plan.json'),'original_qualification':ref(U/'qualification.json'),'history':ref(HERE/'historical-budget.json'),'history_source':ref(U/'paid-work/private/sonnet-budget.json'),'accounting':ref(U/'paid-work/public/live-accounting.json'),'outcome':ref(U/'paid-work/public/m1-sonnet-remote-useful-03-result.json'),'carry_tokens':144004,'charged_requests':2,'proposed_policy':{'limit':500000,'preventive':480000,'max_requests':4},'currently_authorized_limit':200000,'new_requests_max':2,'request_ids':{'useful':'m1-sonnet-remote-useful-05','continuation':'m1-sonnet-remote-continuation-06'},'original_source_pins':{n:ref(U/n) for n in names},'authorization_record_created':False,'services_provider_effects':0,'prepared_work_plan':False})
