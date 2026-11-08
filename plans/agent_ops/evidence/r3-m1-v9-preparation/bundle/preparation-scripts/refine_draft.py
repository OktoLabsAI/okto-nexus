"""Complete textual v9 accounting alignment before the preparation freeze."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).parent/'draft'
path=ROOT/'m1-codex-campaign-proposal-v9.json'
p=json.loads(path.read_text(encoding='utf-8'))
policy=p['controller_preparation']['policy']; ancestry=p['controller_preparation']['ancestry']
p['token_accounting'].update(admissions_carry_in=3,cumulative_admissions_maximum=9,
    previous_preventive_threshold=200000,counter_semantics=p['finite_work']['counter_semantics'])
p['token_accounting']['algorithm'][0]='Carry in 3 conservative reservations and 45843 observed tokens once; preserve the v8 fault/checkpoint and earlier v7 ancestry. Reservation is not proof of inference.'
c=p['controller_preparation'];c['approval_schema'].update(proposal_revision=9,policy=policy,ancestry=ancestry)
c['approval_schema_is_template']=True
c['historical_v8_synthetic_cases']=c.pop('recorded_final_synthetic_tests',23)
c.pop('review',None);c['v9_qualification']=None
p['transport_reuse'].update(status='DRAFT_COMPOSITION_REQUIRES_V9_QUALIFICATION',
    controller='V9 policy/ancestry/receipt/state-format delta from qualified v8 revision2; no v9 test result yet.')
p['publication_helper']['qualification_scope']='Historical qualification of the byte-identical helper, not a new v9 campaign result.'
for step in p['steps']:
    step['commands_are_reference_only']=True
    step['dispatch_rule']='Use only the frozen approved finite campaign wrappers; these CLI/API references are not standalone dispatch authority.'
p['steps'][0]['gate']='New Nexus GET check-recovery wheel and exact unchanged Core/Connector artifacts qualified and pinned; no personal configuration read.'
step=next(s for s in p['steps'] if s['id']=='05-connector-root-review-finish')
step['commands']=step['commands'][:3]+['<QUALIFIED_PYTHON> -I -B m1_v9_remote_setup.py <exact proposal and approval selectors> transfer']
installer=ROOT/'installation/timed_install.py'
installer.write_text(installer.read_text(encoding='utf-8').replace('current v8 proposal','current v9 proposal'),encoding='utf-8')
digest=hashlib.sha256(installer.read_bytes()).hexdigest()
p['base06_installation']['script_sha256']=digest
p['execution_bundle']['files']['timed_install']['sha256']=digest
path.write_text(json.dumps(p,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
print(json.dumps({'proposal_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'status':p['status']}))
