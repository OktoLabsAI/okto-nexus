"""Close the public allowlist after the three touched entry guards pass."""
from pathlib import Path
import hashlib,json

ROOT=Path(__file__).parent
OLD=ROOT/'history-reviewed-v1'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(name,value):(ROOT/name).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
guards=json.loads((ROOT/'guard-result.json').read_text())
assert guards['unique_cases']==3 and guards['effects']=={'popen':0,'socket':0,'vault':0}
assert all(sha(ROOT/name)==value for name,value in guards['inputs'].items())
unchanged=['campaign_context.py','m1_v8_lifecycle.py','m1_v8_setup.py','m1_v8_work.py',
           'supervisor_check.py','publication.py','response_loss.py','test_installed_fg_guard.py']
assert all(sha(ROOT/name)==sha(OLD/name) for name in unchanged)
proposal=json.loads((ROOT/'m1-codex-campaign-proposal-v8.json').read_text())
assert not Path(proposal['paths']['campaign_root']).exists()
assert all(sha(row['path'])==row['sha256'] for row in proposal['execution_bundle']['files'].values())
write('composition-proof.json',{
 'status':'READY_FOR_EXECUTION_REVIEW','execution_authorized':False,
 'entry_guards':{'current_unique_cases':3,'sha256':sha(ROOT/'guard-result.json'),
     'scope':'Only touched remote wrapper refusal guards, zero dispatch. No approved execution tested.'},
 'historical_entry_guards':{'cases':12,'path':'history-reviewed-v1/guard-result.json',
     'sha256':sha(OLD/'guard-result.json'),
     'limit':'Historical refusal tests remain valid within their scope; they did not detect or qualify the handoff race.'},
 'unchanged_files':{name:sha(ROOT/name) for name in unchanged},
 'installed_fg_guards':{'cases':3,'sha256':sha(ROOT/'installed-fg-guard-result.json'),'rerun':False},
 'historical_snapshot':{'path':'history-reviewed-v1/manifest.json','sha256':sha(OLD/'manifest.json'),'review_status':'REJECTED_HANDOFF_ORDERING_RACE'},
 'helper_manifest_sha256':proposal['execution_bundle']['pty']['manifest_sha256'],
 'target_products_absent':True,'installation_not_executed':True,'static_compile':'PASS',
 'explicit_lifecycle_commands':8,'implicit_scheduler_start_maximum':1,
 'no_provider_service_vault_native_execution':True,'no_real_authorization_receipt_created':True})
adaptation=json.loads((ROOT/'publication-adaptation.json').read_text())
adaptation['guard_result_sha256']=sha(ROOT/'guard-result.json')
adaptation['qualification_limit']='Publication helper and work source unchanged from the historical snapshot. Ten focused helper tests and 12 historical entry refusal cases remain historical; this revision reran only three remote-wrapper denial guards. No approved work path executed.'
write('publication-adaptation.json',adaptation)
excluded={'manifest.json','guard-invalid-receipt.json','freeze_bundle.py'}
files=[p for p in ROOT.iterdir() if p.is_file() and p.name not in excluded]
files+=list(OLD.iterdir())
assert all(p.is_file() for p in files)
files.sort(key=lambda p:p.relative_to(ROOT).as_posix())
manifest={'format':'okto.m1.preparation.bundle','revision':8,'preparation_revision':6,
 'status':'READY_FOR_EXECUTION_REVIEW','execution_authorized':False,
 'proposal_sha256':sha(ROOT/'m1-codex-campaign-proposal-v8.json'),
 'files':[{'path':p.relative_to(ROOT).as_posix(),'sha256':sha(p),'bytes':p.stat().st_size} for p in files],
 'excluded':['guard-invalid-receipt.json','obsolete root freeze_bundle.py','__pycache__'],
 'scope':'Three current entry guards; prior 12 refusal guards, three installed FG cases and rejected composition preserved as immutable history. No live execution.'}
write('manifest.json',manifest)
print(json.dumps({'manifest_sha256':sha(ROOT/'manifest.json'),'payloads':len(files),'proposal_sha256':manifest['proposal_sha256']}))
