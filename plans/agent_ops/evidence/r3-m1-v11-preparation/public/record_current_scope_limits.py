"""Record observed coverage honestly while the literal CLI shim is under review."""
from pathlib import Path
import json,hashlib
R=Path(__file__).resolve().parent;D=R/'draft';P=D/'m1-codex-campaign-proposal-v11.json'
with (D/'preparation-history/pre-cli-scope-correction-proposal.json').open('xb') as f:f.write(P.read_bytes())
p=json.loads(P.read_bytes())
limit={'status':'OFFLINE_PARTIAL_SCOPE_NOT_M1_APPROVAL_READY',
    'work_path':'m1_v11_work.py -> installed adapters.inbound.cli.work.open_work -> installed application.terminal_work.TerminalWork -> canonical HTTP; SerialFlow/Controller serialize and fence API effects.',
    'work_cli_parser_executed':False,'literal_cli_reentry_qualified':False,'dashboard_open_close_exercised':False,
    'scope':'The existing wrapper proves application-flow behavior when executed; it does not invoke work CLI parser/rendering or establish literal terminal/dashboard closure.',
    'real_cli_when_authorized':['service lifecycle','setup/connect','remote bootstrap'],
    'no_execution_in_preparation':True,'no_m1_or_dx39_dx40_ac11_promotion':True,
    'frontend_distinction':'SVC-09 concerns version/upgrade; SVC-T09 concerns closing terminal/dashboard while service-owned work survives. No logout/reboot or dashboard event is inferred.',
    'pending':'Review the minimal literal work CLI shim before final campaign scope approval.'}
p['scope_qualification']=limit
p['finite_work']['remote_return_scope']='Reopen the temporary wrapper and installed TerminalWork checkpoint for the same Connector work; literal human CLI parser restart is not covered by this wrapper. Do not rerun Connector identity registration or claim physical host reconnection.'
for row in p['fixed_plan_map']:
    if row['requirement'] in ('M1 / DX-T39','M1 / DX-T40','DX-T47 / DX-T50'):
        row['proof']='Pending literal work CLI coverage. Current wrappers use installed TerminalWork and canonical HTTP/checkpoint recovery; planned outcomes are not yet execution evidence. No promotion follows from this offline composition.'
for step in p['steps']:
    if any('<NEXUS> work ' in command for command in step.get('commands',[])):
        step['coverage_limit']='Reference CLI argv only; current work wrapper calls installed TerminalWork without invoking work CLI parser. Literal CLI M1 evidence remains pending.'
p['status']='OFFLINE_PARTIAL_COMPOSITION_CLI_SCOPE_REVIEW_PENDING_NOT_AUTHORIZED'
p['blocking_preconditions'].insert(0,'Resolve literal work CLI coverage; current wrapper is installed TerminalWork plus canonical HTTP, not work CLI parser/re-entry.')
P.write_bytes((json.dumps(p,indent=2,ensure_ascii=False)+'\n').encode())
(D/'scope-limits-before-cli-review.json').write_bytes((json.dumps(limit,indent=2)+'\n').encode())
print(json.dumps({'status':p['status'],'proposal_sha256':hashlib.sha256(P.read_bytes()).hexdigest(),'runtime_modified':False}))
