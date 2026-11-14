"""Finite public report; no campaign data, database or home is copied."""
import hashlib
import json
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parent
REPO=Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
SITE=Path('C:/Users/jpamb/AppData/Local/Temp/m1-recovery-diagnostics-installed-xtfm5o4x/venv/Lib/site-packages')
PUBLIC=ROOT/'public';PUBLIC.mkdir()
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
sources=[
 'bootstrap/embedded_dispatch.py','bootstrap/embedded_tools.py','bootstrap/runtime_host.py',
 'adapters/outbound/execution/embedded.py','application/execution_local_launch.py',
 'application/execution_leases.py','application/execution_capabilities.py',
 'application/runtime_access.py','application/execution_operator_authority.py',
 'adapters/outbound/sqlite/execution_agent_revisions.py',
 'adapters/outbound/sqlite/connection.py','adapters/outbound/sqlite/write_gate.py',
 'bootstrap/embedded_agent_recovery.py',
]
pins={}
for rel in sources:
    source=REPO/'src/okto_nexus'/rel;installed=SITE/'okto_nexus'/rel
    pins[rel]={'reviewed_source':str(source),'source_sha256':sha(source),
              'installed':str(installed),'installed_sha256':sha(installed),
              'normalized_text_equal':source.read_text(encoding='utf-8')==installed.read_text(encoding='utf-8')}
assert all(x['normalized_text_equal'] for x in pins.values())
evidence=REPO/'plans/agent_ops/evidence/r3-m1-v9-execution/diagnosis/reconciliation.json'
report={
 'status':'OFFLINE_DIAGNOSIS_HISTORICAL_ROOT_CAUSE_UNCONFIRMED',
 'historical_evidence':{'path':str(evidence),'sha256':sha(evidence),
     'retained_facts':['PREPARATION_FAILED with native_absent=1 and no admitted work dispatch',
        'session capability issued; session tool credential eventually REMOVED',
        'DB_ERROR without original SQLite code/phase at28.180058s'],
     'not_inferred':['which call failed','whether a writer was held','whether elapsed time was SQLite wait',
                     'provider consumption or final billing']},
 'source_pins':pins,
 'call_path_after_tool_vault_store':[
   {'source':'bootstrap/embedded_tools.py:127-136','calls':'vault.store -> persisted writer -> launch.check','transaction_boundary':'persisted opens and closes its own writer UoW; launch.check follows after return'},
   {'source':'bootstrap/embedded_tools.py:95-96; application/execution_local_launch.py:57-66,100-137','calls':'owner.verify read; launch.check -> current_agent_revisions writer, then separate read UoW; filesystem checks outside UoW; repeat database comparison','transaction_boundary':'No enclosing product UoW identified across these awaits or filesystem checks'},
   {'source':'adapters/outbound/execution/embedded.py:50-75','calls':'local_launch_factory -> host.acquire -> begin_r4_lease_request -> request_grant -> install_r4_lease -> executor return','transaction_boundary':'Nexus factory work is offloaded; host Core journals are separate files/owners'},
   {'source':'bootstrap/embedded_dispatch.py:427-445; application/execution_leases.py:78-93,225-281','calls':'verify -> leases.issue directly in worker; _parse refreshes revisions before issuance writer','transaction_boundary':'No HTTP-to-self; RuntimeAccessService.authorize uses supplied uow (nullcontext), not a nested writer'},
 ],
 'findings':[
   {'classification':'NO_POSITIVE_DEADLOCK_EVIDENCE','detail':'Reviewed active path does not retain a Nexus UoW across its external vault call, Core await, or direct lease callback. Session gate is asyncio memory synchronization, not a DB transaction.'},
   {'classification':'PLAUSIBLE_CONTENTION_MECHANISM','detail':'current_agent_revisions defaults persist=True and requests a writer even for unchanged revisions. Multiple post-store checks can wait on unrelated concurrent writers. This mechanism is reproduced synthetically, not attributed to V9.'},
   {'classification':'HISTORICAL_PHASE_AMBIGUITY','detail':'REMOVED does not prove the earlier STORED update committed: _remove updates by request_id without requiring prior STORED. The post-vault persisted writer remains in the candidate interval.'},
   {'classification':'DIAGNOSTIC_BOUNDARY','detail':'agent runtime history is the fallback diagnostic stage, not a proven failed history-reader call. Both actual local writer-gate timeout and SQLITE_BUSY produce that prefix; current typed diagnostic distinguishes them.'},
 ],
 'reproduction':{'script':'repro.py','result':'result.json','outcome':'5 assertions PASS, direct installed Python exit0',
   'scope':'actual ConnectionFactory/current_agent_revisions/safe diagnostic on minimal synthetic SQLite schema',
   'not_reproduced':'full authorize_r4 or original campaign failure; locks were deliberately held'},
 'existing_regression_boundary':{'path':'tests/execution_r4/test_startup_session_isolation.py:189',
   'test':'test_authorizer_failure_after_core_composition_preserves_healthy_session',
   'scope':'injects OSError after actual composition and verifies refusal/recovery isolation; does not establish SQLite lock cause'},
 'small_followup_if_needed':[
   'A synthetic full-boundary test can retain the real authorizer/lease services and instrument UoW entry/exit depths; use an Event-held writer immediately after fake vault.store, then release and verify progress without native calls.',
   'A paired expiration case can retain exactly one tool request/capability, refuse opening without native admission and assert the new typed gate/SQLite cause is preserved. This would test controlled contention, not retrospectively identify V9.',
   'If another real failure occurs, retain the typed SQLite cause plus a bounded phase identifier for persisted_tools, local_launch_recheck or lease_issue; no messages, SQL, paths or material. Do not increase timeouts or change revision authority based solely on this investigation.'
 ],
 'effects':{'native':0,'provider':0,'HTTP':0,'service':0,'personal_auth_reads':0,'repository_changes':0},
 'limits':['Only own synthetic SQLite files were created/read; no historical campaign DB or personal home was opened.',
           'Current source and installed files match after newline normalization; no change to the qualified environment.',
           'No root-cause fix is proposed or claimed; V9 original exception specificity remains unavailable.']}
(PUBLIC/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
for name in ('repro.py','result.json','curate.py'):shutil.copyfile(ROOT/name,PUBLIC/name)
manifest={'files':{p.name:{'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(PUBLIC.iterdir())},
          'excluded':['synthetic-db','synthetic-home','historical databases','provider homes','credentials','transcripts']}
(PUBLIC/'artifact-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'public':str(PUBLIC),'report_sha256':sha(PUBLIC/'report.json'),
                 'manifest_sha256':sha(PUBLIC/'artifact-manifest.json'),'payloads':len(manifest['files'])}))
