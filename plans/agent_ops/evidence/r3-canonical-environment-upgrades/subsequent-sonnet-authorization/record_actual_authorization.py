"""Record the actual selected user answer; no lifecycle or provider effect."""
from pathlib import Path
import json,sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from successor_policy import HERE,POLICY,authorize,convert
from request_context import read_json,pin,reserve,sha

candidate=read_json(HERE/'candidate.json')
record={'explicit_user_approval':True,'user_response':'Autorizar teto total de 500 mil tokens',
    'response_reference':'call_4b39bde0e4fa44eda87df45f793fd638/question0/userreply',
    'proposal_sha256':candidate['proposal']['sha256'],'policy':POLICY,
    'carry_tokens':144004,'charged_requests':2,'new_requests_max':2,
    'scope':'Same authenticated Claude CLI account, Sonnet; useful05 and conditional same-session continuation06. No historical reset or refund.',
    'root_selection':'Explicit user answer accepted by root; no separate hash/signature requested from user.'}
pin(candidate['proposal']);authorize(record,candidate)
derived=convert(read_json(pin(candidate['history'])),record,candidate)
reserve(HERE/'authorization-record.json',record)
reserve(HERE/'budget-seed-approved.json',derived)
reserve(HERE/'authorization-projection.json',{'status':'USER_AUTHORIZED_BUDGET_ONLY_NO_EXECUTION',
    'response_reference':record['response_reference'],'user_response':record['user_response'],
    'policy':POLICY,'carry_tokens':144004,'charged_requests':2,'new_requests_max':2,
    'authorization_record_sha256':sha(HERE/'authorization-record.json'),
    'approved_seed_sha256':sha(HERE/'budget-seed-approved.json'),
    'original_history_sha256':candidate['history']['sha256'],
    'historical_rows_unchanged':derived['state']['sessions']==read_json(pin(candidate['history']))['state']['sessions'],
    'services_started':0,'provider_calls':0,'os_events':0})
print(json.dumps({name:{'sha256':sha(HERE/name),'bytes':(HERE/name).stat().st_size} for name in
    ('authorization-record.json','budget-seed-approved.json','authorization-projection.json')}))
