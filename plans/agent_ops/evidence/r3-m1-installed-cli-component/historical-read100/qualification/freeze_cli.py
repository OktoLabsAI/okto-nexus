"""Package explicit offline evidence; no real provider/service/credentials."""
from pathlib import Path
import hashlib,json,shutil,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1];Q=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,value):
    with p.open('x',encoding='utf-8') as f:json.dump(value,f,indent=2)
sources=json.loads((Q/'final-run-sources-v2.json').read_text())
assert all(sha(ROOT/name)==digest for name,digest in sources.items()),'FINAL_SOURCE_DRIFT'
v2=Path('C:/Users/jpamb/AppData/Local/Temp/m1-v11-reader-v2-bvlu12cs/qualification/runtime-freeze.json')
assert sha(v2)=='34bc645a74cc5c157b23f04cbd65149dcf60571d186b66ee9fbe8e02b85a744e'
attempts=[]
for p in sorted(Q.glob('*.xml')):
    s=ET.parse(p).getroot().find('testsuite')
    attempts.append({'path':p.name,'sha256':sha(p),'tests':int(s.get('tests')),'failures':int(s.get('failures')),
        'errors':int(s.get('errors')),'seconds':float(s.get('time')),
        'failed_cases':[c.get('name') for c in s.findall('testcase') if c.find('failure') is not None or c.find('error') is not None]})
failure=[]
for pattern in ('test_one_global*/controller.json','test_whole_work*/private/controller.json'):
    path=next((Q/'final-tmp').glob(pattern));data=json.loads(path.read_text())
    failure.append({'case':path.parent.parent.name if path.parent.name=='private' else path.parent.name,
                    'faults':data['faults'],
                    'request_errors':{name:r['first_observation_error'] for name,r in data['requests'].items() if 'first_observation_error' in r},
                    'maximum_poll_ms':data['independent_observation']['budgets']['maximum_previous_poll_ms']})
write(Q/'timing-failure-projection.json',failure)
runtime=sorted([p for p in (ROOT/'controller').glob('*.py') if not p.name.startswith('test_')]+[ROOT/name for name in ('m1_v11_work.py','publication.py','response_loss.py')])
tests=sorted((ROOT/'controller').glob('test_*.py'))
final=ET.parse(Q/'final.xml').getroot().find('testsuite')
cli_cases=[c for c in final.findall('testcase') if 'test_cli_flow' in c.get('classname','')]
assert len(cli_cases)==11 and all(c.find('failure') is None and c.find('error') is None for c in cli_cases)
report={
 'classification':'CLI_COMPONENT_PASS_WITH_COMPOSITION_TIMING_FAILURES',
 'scope':'Offline harness implementation and tests only. No provider inference, real credential access, service execution, product or wheel modification. Prior v2freeze preserved.',
 'final_full_suite':{'tests':int(final.get('tests')),'passed':61,'failed':int(final.get('failures')),'errors':int(final.get('errors'))},
 'installed_cli_component':{'tests':11,'passed':11,'parser_and_handler':'okto_nexus.adapters.inbound.cli.work.run_work',
     'actual_factory_and_application':'Installed open_work and TerminalWork in11focused cases; synthetic in-memory HTTP.',
     'remote':'Installed RemoteTarget.inspect and RemoteTerminalConnection validation; OperatorProfile supplied a synthetic HTTP client. No claim of real credential authentication.',
     'wrapper_composition':'Four wrapper cases initially passed with installed parser/handlers and synthetic factory flows. Final full run retained the real100ms/600ms observers and failed two timing cases.'},
 'changes':[
   'CLIFlow executes send/status/events/answer-review/answer-decision and continuation on the existing single API worker.',
   'Installed parser, target resolution, readiness, profile guard, checkpoint and display remain active. Only open_work delegates through an observational factory hook.',
   'The wrapper no longer holds a duplicate outer profile guard. Under the installed CLI guard, the original factory result is checked against the previously reserved home/profile/actor/scope/session, including an expected absent session.',
   'Original method results and errors are retained privately; display writes naturally to the outer runner private stdout. No process-global stdout redirect or stdout-as-accounting-authority was introduced.',
   'Exit3 alone does not imply transport failure. Domain failed/blocked states remain explicit; known original errors retain their identity and response-loss metadata. A completed handler with failed CLI presentation becomes CLI_OUTCOME_UNCONFIRMED with possible_effect in the retained outcome.',
   'events exit classification follows the actual presented event-page projection while returning the complete observation to the existing configuration observer.',
   'Known-loss recovery uses GET-only status/events/answer-review and existing receipt GETs. resume is not exposed because the installed resume may submit an admission.',
   'Existing effect fence/counting/FiniteResponseLoss and one global reservation ledger are reused; no duplicate POST validator or new effect retry path was added.'
 ],
 'unchanged_policy':{'revision':11,'carry_in_admissions':6,'carry_in_tokens':89473,'max_new_admissions':5,'max_cumulative_admissions':11,
                     'preventive_tokens':200000,'tolerance_tokens':700000,'deadline_seconds':120,
                     'initialization_ms':250,'read_ms':100,'poll_ms':600,'freshness_ms':1000},
 'attempts':attempts,
 'preserved_initial_fixture_failure':'Five initial CLI test failures arose from fixture profile agent-local versus selected scope agent-a. Corrected the fixture to use its actual selected agent; runtime gates were not relaxed.',
 'preserved_runner_failure':'First isolated runner stopped before pytest because it attempted nonexistent unused module nexus_connector. Corrected origin list to the installed Nexus/Core modules actually exercised; initial source snapshot retained.',
 'timing_failures':failure,
 'review_fixes':['Root: events display projection; strict expected-session comparison includingNone.',
                 'Independent preparation review: post-classification outcome metadata must preserve possible_effect for presentation failure.'],
 'qualification_limits':[
   'No all-green final composition claim:61/63passed. Core observations of211.2865ms and153.5869ms exceeded100ms; one resulting poll reached740.4216ms. Existing fail-closed behavior denied success.',
   'All11new installed CLI component cases passed; this does not override composition timing failures or prove statistical availability.',
   'run_work was invoked as the installed Python parser/handler entrypoint, not a fresh console executable subprocess. No TTY/chat, human interactive shell or dashboard-switch cycle was claimed.',
   'DX-T39/T40/AC11 remain pending actual approved useful harness/provider work through the two topologies. Synthetic parser proofs and preparation are not that real acceptance.',
   'The finite campaign supports the preapproved permission decision without an answer file; arbitrary interactive answer-file responses are intentionally outside this increment.',
   'Readiness GET precedes the factory transport hook and remains the real installed inspection path. Subsequent effects still cross the current-clock fence; OS IO is not preemptible.'
 ],
 'predecessor_v2_freeze_sha256':sha(v2),'module_origins_sha256':sha(Q/'module-origins.json'),
 'final_sources_sha256':sha(Q/'final-run-sources-v2.json')}
write(Q/'qualification.json',report)
manifest={'classification':report['classification'],'policy_revision':11,
          'runtime':[{'path':p.relative_to(ROOT).as_posix(),'sha256':sha(p)} for p in runtime],
          'tests':[{'path':p.relative_to(ROOT).as_posix(),'sha256':sha(p)} for p in tests],
          'qualification_sha256':sha(Q/'qualification.json'),'predecessor_v2_freeze_sha256':sha(v2)}
write(Q/'runtime-freeze.json',manifest)
public=Q/'public-allowlist';public.mkdir()
items=[]
artifacts=runtime+tests+sorted(Q.glob('*.xml'))+[Q/name for name in ('qualification.json','runtime-freeze.json',
    'timing-failure-projection.json','module-origins.json','final-run-sources.json','final-run-sources-v2.json','run_final.py','freeze_cli.py')]
for p in artifacts:
    relative=p.relative_to(ROOT);out=public/relative;out.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,out)
    items.append({'path':relative.as_posix(),'sha256':sha(out),'bytes':out.stat().st_size})
write(Q/'public-allowlist.json',{'files':items,'excludes':['database files','private fixture ledgers','real stdout','credentials','venv','pycache']})
print(json.dumps({'runtime_freeze_sha256':sha(Q/'runtime-freeze.json'),'public_allowlist_sha256':sha(Q/'public-allowlist.json'),
                  'qualification_sha256':sha(Q/'qualification.json'),'files':len(items),'classification':report['classification']},indent=2))
