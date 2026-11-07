from pathlib import Path
import ast
import hashlib
import json
import tempfile
import xml.etree.ElementTree as ET

repo=Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
out=Path(tempfile.mkdtemp(prefix='r3-contract-closure-'))
ev='plans/agent_ops/evidence/'
current=ev+'r3-cooperative-drain/installed/nexus-installed-v1/canonical/tests.xml'
recovery=ev+'r3-cooperative-drain/installed/nexus-installed-fixture-retry/canonical/tests.xml'
rows=[]
def row(criterion,path_name,assertion,sources,proofs,limits):
    evidence=[]
    for xml,functions in proofs:
        p=repo/xml
        cases=list(ET.parse(p).iter('testcase'))
        selected=[]
        for function in functions:
            found=[c for c in cases if c.attrib['name'].split('[')[0]==function]
            assert found,(xml,function)
            assert all(c.find('failure') is None and c.find('error') is None and c.find('skipped') is None for c in found),(xml,function)
            selected.extend(c.attrib['classname']+'::'+c.attrib['name'] for c in found)
        evidence.append({'path':xml,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'passed_cases':sorted(set(selected))})
    source=[]
    for path in sources:
        p=repo/path
        source.append({'path':path,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
    rows.append({'criterion':criterion,'entry_path':path_name,'assertion_reviewed':assertion,'current_sources':source,'evidence':evidence,'limits':limits})
row('AC-05','message/handoff creation and canonical approval',
    'One persisted client request resolves the same message/handoff/approval; DB commit and receipt are atomic. Before/after process death resumes that request; approval.granted remains one.',
    ['src/okto_nexus/application/terminal_coordination.py','tests/test_coordination_creation.py','tests/test_coordination_requests.py','tests/execution_r4/test_coordination_cli.py'],
    [(ev+'pr05-coordination-creation-installed.xml',['test_real_process_exit_during_approval_resumes_original_request','test_process_termination_at_commit_boundary']),
     (ev+'pr05-coordination-cli-behavior-installed.xml',['test_real_process_death_after_commit_recovers_through_installed_entrypoint']),
     (recovery,['test_restart_after_commit_recovers_original_without_another_creation','test_missing_previously_confirmed_receipt_is_uncertain_and_never_recreated'])],
    'Historical installed actual SQLite/HTTP/CLI process death composes with current same-facade recovery. No universal exactly-once outside receipt retention.')
row('AC-05','participant cooperation exchange and handoff',
    'Separate consent and fixed request IDs survive failure before/after transmission, request-file and consent-file failures. Missing/expired receipts cause uncertainty, never recreation. Actual CLI death preserves one exchange message.',
    ['src/okto_nexus/application/terminal_cooperation.py','tests/test_terminal_cooperation.py','tests/execution_r4/test_cooperation_cli.py'],
    [(recovery,['test_crash_recovery_preserves_one_effect_and_same_ids','test_lost_response_and_missing_checkpoint_only_inspect_prior_consent','test_missing_request_file_does_not_reset_a_confirmed_request_window']),
     (ev+'pr04-cooperation-facade-cli-installed.xml',['test_real_process_death_after_exchange_commit_recovers_installed_entrypoint'])],
    'Unit fault injection and actual CLI/HTTP/SQLite; no real client/provider M2 qualification.')
row('AC-05','productive work submission and native decision',
    'Lost intent-resolution/operation response reopens the same operation; one native opening and send. Lost decision response resolves the original canonical decision and one native answer without storing private response text.',
    ['src/okto_nexus/application/terminal_work.py','tests/execution_r4/test_terminal_work.py'],
    [(recovery,['test_lost_submission_response_recovers_same_work_without_duplicate_dispatch','test_native_decision_response_loss_recovers_canonical_result_and_keeps_answers_out_of_profile'])],
    'Current installed canonical services and synthetic native peers; real active-provider interruption is AC14, still open.')
row('AC-05','local participant initialization, launch and identity Finish',
    'Credential/file checkpoints observe the original intent; uncertain launch does not respawn; current file drift is preserved. Finish recovers one reviewed identity without rotating its key.',
    ['tests/execution_r4/test_participant_init.py','tests/execution_r4/test_participant_launch.py','tests/execution_r4/test_terminal_identity.py'],
    [(recovery,['test_lost_checkpoint_resumes_same_intent_by_observing_effect','test_uncertain_file_with_later_edit_is_preserved_without_new_intent','test_checkpoint_loss_preserves_uncertainty_without_respawn','test_finish_creates_one_reviewed_identity_and_recovery_never_rotates_its_key'])],
    'Current installed simulated credential/client mechanisms; no complete real credential-to-client chain claimed.')
row('AC-05','remote bootstrap review, human approval and host Finish',
    'Lost bootstrap/decision/checkpoint replies retain original references, approval and Finish. The host Finish is the only completion authority; receipt recovery does not reissue setup.',
    ['tests/execution_r4/test_remote_terminal_setup.py'],
    [(recovery,['test_lost_bootstrap_response_recovers_references_without_reissue','test_lost_decision_resumes_same_approval_then_only_host_finish_completes','test_checkpoint_failure_after_bootstrap_reports_uncertainty_without_reissue'])],
    'Current installed canonical operator/host protocol, synthetic native peer; remote real provider work remains M1.')
row('AC-15','Nexus status/logs/default doctor observations',
    'Absent homes remain absent; logs do not require launching saved Python. Unreachable live owners are not declared stopped. Default doctor does not initialize/start the service.',
    ['tests/test_service_inspection.py','tests/test_service_logs.py','tests/test_project_doctor_cli.py'],
    [(ev+'pr03-project-doctor-installed.xml',['test_absent_instance_is_not_started_or_initialized','test_status_of_absent_instance_does_not_create_home_or_start_process','test_unreachable_live_owner_is_not_reported_as_stopped']),
     (ev+'pr02-nexus-service-logs-installed.xml',['test_absent_logs_are_passive_and_do_not_require_saved_python','test_unavailable_log_is_not_inferred_as_stopped'])],
    'Historical installed passive contracts retained; unchanged diagnostic behavior reviewed. No inference or credential access attributed to passive observation.')
row('AC-15','Nexus start/stop/restart/foreground',
    'Actual detached process survives launcher exit, reuses owner and drains. Restart refuses pending/unknown stop. Foreground SIGINT/SIGTERM/HTTP retains HTTP and process until resource release. Current force remains explicit and generation-bound.',
    ['tests/test_service_process.py','tests/test_service_start.py','tests/execution_r4/test_server_signal_shutdown.py','tests/test_service_drain_decision.py'],
    [(ev+'pr02-nexus-service-logs-installed.xml',['test_concurrent_detached_start_survives_cli_exit_reuses_and_drains']),
     (current,['test_restart_does_not_start_when_drain_is_pending','test_unconfirmed_exit_does_not_authorize_restart','test_signal_keeps_serve_process_and_http_until_inventory_release','test_force_cli_requires_explicit_stop_and_generation','test_timeout_does_not_start_shutdown_or_reopen_admission'])],
    'Actual Windows disposable processes and synthetic native peers; registered Task Scheduler actions remain AC13, not inferred here.')
row('AC-15','Connector passive observations',
    'Status/logs/doctor preserve absent or existing state, do not initialize vault/start daemon, and keep redacted diagnostic output. Explicit credential resolution differs from default status.',
    ['../okto-nexus-connector/docs/service-lifecycle.md'],
    [(ev+'pr02-connector-passive-installed.xml',['test_cli_observation_never_initializes_an_absent_instance','test_absent_instance_stays_absent','test_existing_snapshot_is_not_rewritten_or_locked','test_logs_are_persisted_redacted_and_filtered'])],
    'Historical installed Connector contract; actual registered user-task operation remains unexecuted.')
row('AC-05','reviewed grant renewal and issuance receipt recovery',
    'Existing usable authority refuses duplicate issuance. Lost response resolves one issuance receipt and two total grants (old expired plus new); subsequent revocation never reissues or revives that grant.',
    ['src/okto_nexus/application/terminal_authorization.py','tests/execution_r4/test_terminal_authorization.py'],
    [(ev+'pr03-remote-renewal/candidate-v2/nexus/installed.xml',['test_available_grant_is_observed_without_duplicate_authority','test_uncertain_issue_recovers_same_receipt_even_after_later_revocation'])],
    'Historical installed canonical renewal, actual current grant authority remains mandatory; no provider work implied.')
row('AC-15','current Nexus and Connector detached lifecycle plus Connector foreground ownership',
    'Both current installed CLIs survive launcher exit, reuse one owner, restart into a new generation and drain canonically. Stale generation/token cannot stop or replace the new owner. Connector foreground acquires exclusion before initializing state/vault.',
    ['tests/test_service_process.py','../okto-nexus-connector/tests/integration/test_detached_service_lifecycle.py','../okto-nexus-connector/tests/unit/test_user_service_lifecycle.py'],
    [(ev+'r3-contract-closure/controls/tests.xml',['test_concurrent_detached_start_survives_cli_exit_reuses_and_drains','test_concurrent_cli_start_reuse_restart_and_drain_keep_one_owner']),
     ('../okto-nexus-connector/docs/evidence/cooperative-drain/installed/installed.xml',['test_production_foreground_owns_lock_before_state_or_vault_initialization','test_stop_latches_before_ipc_and_preserves_canonical_drain'])],
    'Two new runs of existing tests in isolated profiles with exact current wheels; neither registers native tasks nor invokes provider work.')
report={'scope':'Finite contract closure for AC05 and AC15; real M1/M2/provider/native task gates remain separate','new_test_runs':2,'product_changes':0,'rows':rows,
    'AC05_boundary':'Only documented idempotent request/receipt windows and named current paths; no automatic replay of uncertain requests and no guarantee after tombstone expiry.',
    'AC15_remaining':'No missing literal control/passivity contract identified. Registered native task qualification belongs to AC13 and remains open.',
    'recommended_status':{'AC-05':'VERIFIED','AC-15':'VERIFIED'}}
(out/'matrix.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(out/'build_matrix.py').write_bytes(Path(__file__).read_bytes())
print(json.dumps({'output':str(out),'rows':len(rows),'passed_case_references':sum(len(e['passed_cases']) for r in rows for e in r['evidence'])}))
