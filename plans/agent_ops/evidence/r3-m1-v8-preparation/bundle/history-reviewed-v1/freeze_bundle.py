"""Curate one finite proposal and its references. No installation or campaign."""
from pathlib import Path
import ast,hashlib,json,xml.etree.ElementTree as ET
ROOT=Path(__file__).parent
TEMP=ROOT.parent
PRIOR=TEMP/'m1-v8-final-preparation-s9znxbz8'
INSTALL=TEMP/'m1-base06-install-g9ii2zhe'
PTY=TEMP/'m1-protected-pty-j_c21e97'
HELPER=PTY/'revision-4'
COMPONENT=TEMP/'m1-controller-v8-bfx9ol3t/revision-2/public'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(name,value):(ROOT/name).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
def verify_manifest(path,expected):
    assert sha(path)==expected
    value=json.loads(path.read_text())
    entries=value['files'] if 'files' in value else value['artifacts']
    for name,record in entries.items():assert sha(path.parent/name)==record['sha256'],name
    return len(entries)

helper_manifest=HELPER/'public/artifact-manifest.json'
helper_count=verify_manifest(helper_manifest,'2e16e187edc8fe2a67621e5279ed5d8b9c3eb96adc7d573ce7d6cd130f45b4b2')
install_manifest=INSTALL/'public/artifact-manifest.json'
install_count=verify_manifest(install_manifest,'43d2232b2cc2d7d39eba0fe8a36612d04a2262bd299e4986e28761eeebe708fe')
contract=json.loads((INSTALL/'base06-contract.json').read_text())
assert sha(contract['script'])==contract['script_sha256']=='c7b4ff53aac0ac0c121557320b146d5536775fc20f2b388e0a2af2b334c5955e'
assert sha(INSTALL/'products-requirements.txt')==contract['requirements_sha256']
assert sha(INSTALL/'dependency-manifest.json')==contract['dependency_manifest_sha256']
assert not Path(contract['result']).exists() and not Path(contract['reservation']).exists()
assert json.loads(Path(contract['preparation']).read_text())['products_installed'] is False
target=Path(contract['python_prefix']);site=target/'Lib/site-packages'
for name in ('okto_nexus','okto_nexus_connector','nexus_connector_core'):assert not (site/name).exists()
assert sha(HELPER/'protected_pty.py')=='4103c02b29cbdb356d7040fdc151d2e6067183bfb7e3ec067c1a0318f19d6e98'
assert sha(HELPER/'owned_job.py')=='1b6923d36a9ec047bc67b66d898eac017cd9f7930969e8f894330d0eca56570c'
dependency=json.loads((PTY/'public-v2/dependency-proof.json').read_text())
for name,record in dependency['package_payloads'].items():assert sha(PTY/'venv/Lib/site-packages'/name)==record['sha256']

proposal=json.loads((PRIOR/'m1-codex-campaign-proposal-v8.json').read_text())
proposal['preparation_revision']=5
proposal['status']='READY_FOR_EXECUTION_REVIEW'
proposal['execution_authorized']=False
proposal['previous_preparation']={'path':str(PRIOR/'m1-codex-campaign-proposal-v8.json'),'sha256':sha(PRIOR/'m1-codex-campaign-proposal-v8.json')}
proposal['base06_installation']=contract
proposal['base06_installation']['public_manifest']={'path':str(install_manifest),'sha256':sha(install_manifest)}
proposal['base06_installation']['invocation']=[contract['python'],'-I','-B',contract['script'],
    '--proposal','<FINAL_PROPOSAL_PATH>','--expected-proposal-sha256','<FINAL_PROPOSAL_SHA256>',
    '--approval-path','<ACTUAL_APPROVAL_RECEIPT>','--approval-sha256','<ACTUAL_RECEIPT_SHA256>','--execute']
old_prefix=Path(proposal['package_pins']['python_prefix'])
pins=proposal['package_pins']
pins['qualified_reference_environment']=str(old_prefix)
pins['python_prefix']=str(target);pins['python']=contract['python']
pins['status']='QUALIFIED_ARTIFACTS_INSTALL_REQUIRED'
for row in pins['files']:
    row['path']=str(target/Path(row['path']).relative_to(old_prefix))
    if Path(row['path'])==Path(contract['python']):row['sha256']=sha(contract['python'])
for name,pin in pins['packages'].items():
    pin['qualified_reference_package']=pin['package']
    pin['package']=str(site/name)
    pin.pop('installed_files_verified',None)
    pin.pop('import_path',None)
    pin['expected_payload_files']=pin['files'];pin['installed_at_preparation']=False
proposal['package_pin_status']={'current':'QUALIFIED_WHEELS_TARGET_DEPENDENCIES_ONLY',
    'required':'After approval, one timed offline install must produce the exact matching receipt and982 payload/import verification before any campaign script passes its gate.',
    'not_claimed':'Products are not installed in this target yet; prior qualification was performed in the separate reference environment.'}
commands=json.loads((PRIOR/'proposed-commands.json').read_text())
for step in commands['steps']:step['argv'][0]=contract['python']
commands['package_pin_status']='QUALIFIED_WHEELS_INSTALL_RECEIPT_REQUIRED'
commands['counts'].update(explicit_lifecycle_commands=8,implicit_ensure_start_calls_maximum=1,
    implicit_scheduler_start_maximum=1,maximum_service_start_stop_install_uninstall_effects=9)
commands['implicit_ensure']={'command':'Single Connector connect --setup-receipt consumer',
    'environment_override_consumer_only':{'OKTO_NEXUS_CONNECTER_DAEMON_FG':'1'},
    'allowed':'Reuse ready owner or at most one Scheduler start of the same registered task; no detached fallback.',
    'not_atomic':'Preflight is not a fence; same task/digest/supervisor and post-Finish PID/birth/generation are checked before work.'}
commands['guards']=[guard for guard in commands['guards'] if 'PTY composition' not in guard]
commands['guards'].append('One final explicit approval is still required. Eight explicit commands plus at most one implicit Scheduler start; no force/replay/additional connect --identity.')
write('proposed-commands.json',commands)
bundle=proposal['execution_bundle']
bundle.update(status='FROZEN_QUALIFIED',directory=str(ROOT),qualification_scope='Component synthetic qualification + finite installed branch proof + static composition/entry denials; no live campaign executed.')
bundle['files']={name:{'path':str(ROOT/file),'sha256':sha(ROOT/file)} for name,file in [
 ('context','campaign_context.py'),('lifecycle','m1_v8_lifecycle.py'),('setup','m1_v8_setup.py'),
 ('work','m1_v8_work.py'),('remote_setup','m1_v8_remote_setup.py'),('supervisor_check','supervisor_check.py'),
 ('publication','publication.py'),('response_loss','response_loss.py')]}
for name,path in [('setup_monitor',COMPONENT/'setup_journal.py'),('protected_pty',HELPER/'protected_pty.py'),
 ('owned_job',HELPER/'owned_job.py'),('pty_base_python',Path('C:/Python313/python.exe')),
 ('timed_install',Path(contract['script'])),('install_requirements',INSTALL/'products-requirements.txt'),
 ('install_dependency_manifest',INSTALL/'dependency-manifest.json')]:
    bundle['files'][name]={'path':str(path),'sha256':sha(path)}
for index,(name,record) in enumerate(dependency['package_payloads'].items()):
    bundle['files']['pty_dependency_'+str(index)]={'path':str(PTY/'venv/Lib/site-packages'/name),'sha256':record['sha256']}
bundle['commands']={'path':str(ROOT/'proposed-commands.json'),'sha256':sha(ROOT/'proposed-commands.json')}
bundle['script_selections']['remote_setup']=['transfer']
bundle['pty']={'original_helper_directory':str(HELPER),'public_manifest':str(helper_manifest),'manifest_sha256':sha(helper_manifest),
    'qualified_cases':'Seven revision3 synthetic cases plus three focused revision4 cases; not summed as independent campaign cases.',
    'producer_consumer_concurrent':True,'consumer_only_environment':{'OKTO_NEXUS_CONNECTER_DAEMON_FG':'1'},
    'allowed_job_children':'Disposable canonical CLIs and bounded version/protocol probes only; no productive turn, service or persistent native session.',
    'material':'New own campaign key in memory only, validated unique complete block, delivered once via canonical credential-stdin; no transcript/argv/file exposure.',
    'ambiguity_or_deadline':'Possible effect retained, no replay. Only exact auxiliary Job children may be cleaned; never an external service.',
    'producer_no_json':True,'consumer_omits_non_interactive_and_json':True,'task_postcheck_required':True}
bundle['final_pin_schema']['status']='QUALIFIED_ARTIFACTS_INSTALL_REQUIRED; matching timed installation receipt plus exact actual payload hashes required before execution'
bundle['future_finite_gate']='Root reviews/curates/commits these exact bytes, computes final external proposal digest, then requests actual explicit approval. No approval exists in this preparation.'
proposal['topology']['service_commands']='proposed-commands.json'
proposal['topology']['implicit_scheduler_start_maximum']=1
proposal['authorization_request_summary'].update(explicit_lifecycle_actions=8,implicit_scheduler_start_maximum=1,
    offline_product_installations=1,product_install_prefix=str(target),execution_authorized=False)
proposal['proposed_delta_from_v7']['implicit_scheduler_start_maximum']=1
proposal['proposed_delta_from_v7']['offline_timed_product_installation']=1
proposal['proposed_delta_from_v7']['reason_new_authorization']='The previous cycle is closed. This snapshot adds a fresh installation/homes/tasks, replacement work under new IDs,8 cumulative admissions and proposed200k preventive threshold. Consumed prior force authorization does not apply.'
for step in proposal['steps']:
    if step['id']=='05-connector-root-review-finish':
        step['commands']=[command for command in step['commands'] if '--identity m1v8-remote' not in command]
        step['gate']='Fresh canonical host draft/review, protected concurrent PTY key transfer, exactly one retained transfer reservation, consumer-only FG=1. Existing user service must be observed ready and exact task/digest/supervisor/owner confirmed after Finish before work. One possible Scheduler ensure/start is explicitly proposed.'
    if step['id']=='07-connector-reconnect-and-result':
        step['id']='07-operator-return-and-connector-result'
        step['commands']=[command for command in step['commands'] if '<CONNECTOR>' not in command]
        step['required_evidence']='Close/reopen the operator CLI observer and recover the same work/session/result via canonical GET; one explicit continuation. Does not claim physical Connector host reconnection or replace separate reconnect/lifecycle plan tests.'
proposal['token_accounting']['remote_setup_source']='Canonical remote configuration/probe path sends no model turn. Native probes are ephemeral auxiliary processes. Unknown extra model consumption stops the campaign; no imaginary remote journal or automatic extra turn.'
proposal['finite_work']['remote_return_scope']='Reopen the human operator CLI and recover the same Connector work; do not rerun Connector connect --identity or claim physical host reconnection.'
proposal['transport_reuse']['status']='FINITE_SCRIPTS_CONCRETELY_COMPOSED'
proposal['transport_reuse']['remaining_remote_route']='Resolved by concurrent qualified helper plus consumer FG guard and before/after exact owner checks.'
proposal['publication_helper']['path']=str(ROOT/'publication.py')
proposal['publication_helper']['sha256']=sha(ROOT/'publication.py')
proposal['base06_measurement']={'start':'installation-result timing.install_started_monotonic_ns/UTC',
    'end':'first work result useful_confirmed_monotonic_ns only when expected report and canonical SUCCEEDED receipt agree',
    'preparation_excluded':'Dependency venv copy and synthetic qualifications precede product install timing and are reported separately.',
    'no_claim_before_measurement':True}
proposal['dx43_observation']={'path':'TerminalWork.observe GET canonical session events; replay after_sequence0 for opening metadata when needed.',
    'native_type':'core/codex_thread_configuration',
    'fields':['approvalPolicy','approvalsReviewer','cwd','instructionSources','model','modelProvider','sandbox','reasoningEffort'],
    'retained':'Work result stores closed Core projection with scope/epoch/sequence and reported/missing/invalid statuses.',
    'limits':'References are not read; metadata is not enforcement or a full tools inventory. Unknown remains unknown; no native turn is created to recover this metadata.'}
proposal['blocking_preconditions_before_execution_request']=[]
proposal['preconditions_after_approval_before_effects']=[
 'Verify the final proposal+receipt hashes; no old approval or force permission is inherited.',
 'Run the one offline timed product installer with --execute; receipt must bind this proposal/approval and verify982 payloads/imports/pipcheck.',
 'Recheck task/home/port and all frozen hashes immediately before lifecycle effects; stop on drift.',
 'Create only approved fresh fixtures/homes; canonical account/login/setup review and exact revision precede setup dispatch.',
 'No productive request without controller durable reservation/callbacks/polling. Remote work additionally requires post-PTY exact owner/Finish check.'
]
proposal['evidence_references']={
 'controller':{'manifest':str(COMPONENT/'artifact-manifest.json'),'sha256':sha(COMPONENT/'artifact-manifest.json'),'tests':23},
 'pty':{'manifest':str(helper_manifest),'sha256':sha(helper_manifest)},
 'timed_install':{'manifest':str(install_manifest),'sha256':sha(install_manifest),'gates':27},
 'fg_installed_branches':{'path':str(ROOT/'installed-fg-guard-result.json'),'sha256':sha(ROOT/'installed-fg-guard-result.json'),'cases':3},
 'source_proof':{'path':str(ROOT/'source-proof.json'),'sha256':sha(ROOT/'source-proof.json')},
 'qualified_reference_preflight':{'path':str(PRIOR/'final-preflight.json'),'sha256':sha(PRIOR/'final-preflight.json'),'product_files':982},
 'limits':'Qualification/guard results are preparation only; no approved run, product installation or service/provider execution occurred.'}
write('m1-codex-campaign-proposal-v8.json',proposal)

base=[contract['python'],'-I','-B','-m','okto_nexus.adapters.inbound.cli.main']
host=[contract['python'],'-I','-B','-m','okto_nexus_connector.cli.main','--state-dir',proposal['paths']['connector_state']]
draft=Path(proposal['paths']['public_evidence'])/'connector-draft.json'
planning={
 'status':'EXACT_NONSECRET_COMMANDS_PROPOSED_NOT_EXECUTED','cwd':proposal['paths']['campaign_root'],
 'local_plan':{'argv':base+['connect','--profile','m1v8-local','--client','codex','--project',proposal['paths']['local_project'],
    '--candidate-ref',proposal['native_selection']['candidate_ref'],'--provider-home',proposal['provider_context']['provider_home'],
    '--new-agent','m1v8-local','--plan','--json']+commands['service_selection_args'],
    'result':'Canonical own server_home/terminal/profiles/m1v8-local.json; setup script reads this exact document.'},
 'connector_host_draft':{'argv':host+['connect','--server',commands['origin'],'--harness','codex_app_server',
    '--executable',proposal['paths']['codex_executable'],'--project',proposal['paths']['remote_project'],
    '--provider-home',proposal['provider_context']['provider_home'],'--request-id','m1v8-connector-setup',
    '--setup-draft',str(draft),'--no-start-at-login'],
    'nonsecret_stdin':'1\n','meaning':'Only final Save draft choice, with exact installation/project/provider supplied. Unexpected prompt/choice or mismatching draft stops review; no credential here.'},
 'operator_login':{'argv':base+['operator','login','--profile','m1v8-human','--server',commands['origin'],
    '--username','m1v8-human','--password-stdin','--home',proposal['paths']['operator_home']],
    'stdin':'Generated own password in memory only, from canonical fresh-account bootstrap described in proposal; never a personal credential.'},
 'remote_plan':{'argv':base+['connect','--operator-profile','m1v8-human','--remote-draft',str(draft),
    '--profile','m1v8-remote','--new-agent','m1v8-remote','--plan','--json','--home',proposal['paths']['operator_home']],
    'result':'Canonical own operator_home/terminal/profiles/m1v8-remote.json. Review scope and write public/remote-review-selection.json with exact proposal_sha256/review_revision/server_id/profile before transfer.'},
 'productive_and_transfer_scripts':bundle['script_selections'],
 'cleanup':'Use canonical work close then observe exact exit/PIDbirth and task stopped; lifecycle wrapper uninstall requires cleanup-component.json proof. Stop reservation shared with controller callbacks. No force or duplicate stop.'}
write('planning-commands.json',planning)
for source in ROOT.glob('*.py'):compile(source.read_bytes(),str(source),'exec')
assert not Path(proposal['paths']['campaign_root']).exists()
assert not Path(contract['result']).exists() and not Path(contract['reservation']).exists()
write('composition-proof.json',{'status':'STATIC_COMPOSITION_READY_ENTRY_GUARDS_NEXT','helper_manifest_payloads':helper_count,
    'installer_manifest_payloads':install_count,'helper_origin_preserved':str(HELPER),
    'pty_dependency_payloads_verified':len(dependency['package_payloads']),
    'target_products_absent':True,'installation_not_executed':True,'static_compile':'PASS',
    'explicit_lifecycle_commands':8,'implicit_scheduler_start_maximum':1,
    'no_real_authorization_receipt_created':True,'no_provider_or_service_execution':True})
print(json.dumps({'root':str(ROOT),'proposal_sha256':sha(ROOT/'m1-codex-campaign-proposal-v8.json'),
    'status':proposal['status'],'new_python':contract['python']},indent=2))
