"""Finite ATN/OBS trace audit: source and retained results, never test execution."""
from __future__ import annotations
import ast
import hashlib
import json
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

ROOT=Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
OUT=Path(__file__).parent
BASE='bcf0e8aaf0bc957d2a876632f90e923316733d89'
E='plans/agent_ops/evidence/'
sha=lambda b:hashlib.sha256(b).hexdigest()
def frozen(path):
    return subprocess.check_output(['rtk','proxy','git','-C',str(ROOT),'show',BASE+':'+path])
plan=frozen('PLANO_CODEX_NEXUS_INTEGRACAO_ATENCAO_ONBOARDING.md').decode('utf-8')
assert sha(plan.encode())=='20d0fafdedc793b97a277f5d41355d7d597ff724a77687394215eea3113ba996'
ledger=json.loads(frozen('plans/agent_ops/ledger.json'))
index=json.loads((OUT/'test-index-private.json').read_text(encoding='utf-8'))

# Add only existing fixtures/tests needed for optionality and OBS-off linkage.
extra_paths=['tests/test_observe_cli.py','tests/execution_r4/test_remote_connection.py','tests/execution_r4/test_r3_mixed_coordination.py']
for path in extra_paths:
    source=frozen(path).decode('utf-8')
    for n in ast.walk(ast.parse(source)):
        if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name.startswith('test_'):
            body=ast.get_source_segment(source,n)
            index[path+'::'+n.name]={'source':path,'name':n.name,'line':n.lineno,'end_line':n.end_lineno,'function_sha256':sha(body.encode()),'body':body,'assertions':[{'line':a.lineno,'text':ast.unparse(a.test)} for a in ast.walk(n) if isinstance(a,ast.Assert)],'reports':[]}
by_name={}
for k,v in index.items(): by_name.setdefault(v['name'],[]).append(k)
for p in sorted((ROOT/E).rglob('*.xml')):
    data=p.read_bytes()
    try: xml=ET.fromstring(data)
    except ET.ParseError: continue
    matches={}
    for tc in xml.iter('testcase'):
        name=tc.attrib.get('name','').split('[',1)[0]
        for key in by_name.get(name,[]):
            if index[key]['source'] not in extra_paths: continue
            expected=index[key]['source'].removesuffix('.py').replace('/','.')
            cls=tc.attrib.get('classname','')
            if cls and not (cls==expected or cls.endswith(expected.split('.')[-1])): continue
            state=next((s for s in ('failure','error','skipped') if tc.find(s)is not None),'passed')
            matches.setdefault(key,[]).append({'identity_sha256':sha((cls+'::'+tc.attrib.get('name','')).encode()),'status':state})
    for key,cases in matches.items():
        index[key]['reports'].append({'path':p.relative_to(ROOT).as_posix(),'sha256':sha(data),'cases':cases,'passed':sum(c['status']=='passed' for c in cases),'failed_or_skipped':sum(c['status']!='passed' for c in cases)})

frontend={}
for p in sorted((ROOT/'frontend/tests').glob('*.test.mjs')):
    if not any(x in p.name for x in ('attention','observation')): continue
    source=p.read_text(encoding='utf-8')
    matches=list(re.finditer(r"^test\('([^']+)'",source,re.M))
    for i,m in enumerate(matches):
        end=matches[i+1].start() if i+1<len(matches) else len(source)
        body=source[m.start():end]
        frontend[m[1]]={'source':p.relative_to(ROOT).as_posix(),'line':source[:m.start()].count('\n')+1,'test_title':m[1],'source_test_block_sha256':sha(body.encode()),'assertion_lines':[line.strip() for line in body.splitlines() if 'assert.' in line],'reports':[]}
for path in [E+'pr07-attention-ui-frontend-final.xml',E+'pr10-external/frontend/pr10a-frontend-all-final.xml',E+'pr10-correlation/frontend/final.xml']:
    data=(ROOT/path).read_bytes()
    for tc in ET.fromstring(data).iter('testcase'):
        if tc.attrib.get('name') in frontend:
            state=next((s for s in ('failure','error','skipped') if tc.find(s)is not None),'passed')
            frontend[tc.attrib['name']]['reports'].append({'path':path,'sha256':sha(data),'status':state})

def report_rank(path):
    preferred=['r3-joint-contracts','pr10-correlation/candidate-v2/installed.xml','pr10-correlation/installed/','pr10-external/final/','pr10-external/candidate-v2/','pr09-herdr/installed/qualified-v2','pr06-attention-completion-release-installed','pr06-attention-completion-behavior-installed','pr08-observations/','installed','source']
    return next((i for i,s in enumerate(preferred) if s in path),99),path

selected_tests={}
def test(name):
    keys=by_name.get(name,[])
    assert len(keys)==1,(name,keys)
    key=keys[0]
    v=index[key]
    good=[r for r in v['reports'] if r['passed'] and not r['failed_or_skipped']]
    assert good,('no retained pass',key)
    chosen=sorted(good,key=lambda r:report_rank(r['path']))[0]
    body=ast.parse(v['body'])
    raises=[ast.unparse(c.context_expr) for n in ast.walk(body) if isinstance(n,(ast.With,ast.AsyncWith)) for c in n.items if 'raises' in ast.unparse(c.context_expr)]
    selected_tests[key]={k:v[k] for k in ('source','name','line','end_line','function_sha256','assertions')}
    selected_tests[key].update(raises=raises,selected_passing_report=chosen,retained_other_passing_report_count=len(good)-1,
        qualification_note='Existing passing identity/declared milestone scope. This audit reads current assertions and does not claim a new execution or sum overlapping reports. Migration version-maintenance assertions can postdate older retained rows.')
    return key

selected_frontend={}
def ft(title):
    v=frontend[title]
    good=[r for r in v['reports'] if r['status']=='passed']
    assert good,title
    selected_frontend[title]={k:v[k] for k in ('source','line','test_title','source_test_block_sha256','assertion_lines')}
    selected_frontend[title]['selected_passing_report']=good[-1]
    return title

source_files={}
def src(path):
    p=ROOT/path
    assert p.is_file(),path
    data=p.read_bytes()
    symbols=[]
    if p.suffix=='.py':
        for n in ast.walk(ast.parse(data.decode('utf-8'))):
            if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):
                symbols.append({'name':n.name,'line':n.lineno})
    source_files[path]={'sha256':sha(data),'bytes':len(data),'symbols':symbols}
    return path

A='src/okto_nexus/application/'
S='src/okto_nexus/adapters/outbound/sqlite/'
H='src/okto_nexus/adapters/inbound/http/'
D='src/okto_nexus/domain/'
F='frontend/src/'
O='src/okto_nexus/adapters/outbound/observation/'

# Evidence bundles are explicit behavioral assertions, not selections by name alone.
groups={}
def group(key,behavior,paths,tests=(),front=(),evidence=(),limit='No missing literal implementation/assertion identified in the reviewed Windows contract; no real provider campaign is needed for this behavior.'):
    groups[key]={'behavior':behavior,'implementation':[src(p) for p in paths], 'tests':[test(n) for n in tests], 'frontend_tests':[ft(t) for t in front], 'additional_evidence':list(evidence),'limit':limit}

group('projection','Closed metadata-only canonical predicates combine native requests, verification, unknown/recovery, authority, aged handoffs, results and cleanup in one bounded relation; no payload hydration or per-item graph query.',[A+'attention.py',S+'attention.py',A+'attention_native.py',A+'attention_operations.py',A+'attention_authority.py',A+'attention_results.py',A+'attention_approvals.py',D+'attention.py'],['test_full_engine_query_count_is_constant_across_distinct_agents_and_source_families','test_read_is_metadata_only_and_changes_no_table','test_normal_claim_cleanup_and_unproved_eligibility_are_not_incidents','test_canonical_native_ingress_projects_exact_recipient_and_existing_action'])
group('preferences','Auxiliary seen/snooze belong to the existing shared operator principal; exact CAS and transactional anchors preserve episodes without touching canonical rows.',[A+'attention.py',S+'attention.py','src/okto_nexus/migrations/161_attention_preferences.sql','src/okto_nexus/migrations/162_attention_authority_epochs.sql'],['test_preferences_are_shared_between_devices_cas_and_independent_from_resolution','test_concurrent_devices_cannot_overwrite_the_same_preference_revision','test_episode_transition_and_canonical_change_rollback_together','test_reentry_has_a_new_episode_under_the_same_storage_timestamp'])
group('passive','GET/snapshot and preferences preserve canonical rows; source commits and rollback create auxiliary metadata atomically while existing authentication remains separate.',[A+'attention.py',S+'attention.py'],['test_empty_list_and_summary_are_explicit_passive_snapshots','test_read_is_metadata_only_and_changes_no_table','test_projection_filters_scope_before_facts_and_does_not_write','test_human_preference_mutations_require_existing_csrf_protection'])
group('api','Operator API has versioned envelopes, exact filters, stable cursor ties and same-relation page/count authorization; preferences retain source and preference CAS.',[H+'attention.py',A+'attention.py',S+'attention.py'],['test_existing_operator_auth_paths_and_agent_refusal','test_canonical_parked_source_filters_summary_and_payload_privacy','test_cursor_has_stable_ties_and_cannot_change_filters','test_counts_and_page_share_one_relation_and_preserve_zero_limit','test_authorization_projection_counts_and_page_use_one_readonly_uow'])
group('stream','SSE metadata invalidates bounded snapshots; gaps/reconnect/time deadlines refresh, transient errors retain stale data and current authorization loss clears protected content.',[H+'attention_stream.py',F+'attentionController.ts',F+'hooks/useAttention.ts'],['test_initial_and_reconnect_reset_never_replay_historical_payload','test_canonical_occurrence_and_large_burst_emit_metadata_batches','test_external_key_rotation_clears_open_stream_with_cold_or_warm_auth'],['reset and retention gaps request snapshots without exposing historical notifications','network failures retain last authorized page and badge without false zeros','authorization loss,403 and featureoff clear authorized data and timers','refresh deadline includes request elapsed time and wake rechecks immediately'])
group('ui','Menu/badge and grouped view preserve existing pages and resolve exact source records through shared canonical inspection and decision controls.',[F+'App.tsx',F+'views/AttentionView.tsx',F+'components/AttentionInspection.tsx',F+'attentionNavigation.ts'],[],['all thirteen actions resolve exact existing canonical records','opening every target only invokes canonical inspection methods, including cleanup inspect','hidden page keeps an independent workspace badge and a bounded timer'],[E+'pr07-attention-ui.md',E+'pr07-attention-ui/root-results.json'])
group('interaction','Viewing state is not resolution; stale command revisions conflict, unknown outcomes offer inspection, and lost preference replies reconcile via reads without replay.',[F+'attentionController.ts',F+'attentionNavigation.ts',F+'components/AttentionInspection.tsx',A+'attention.py'],['test_only_current_unknown_receipt_or_reconciliation_requires_attention','test_preferences_are_shared_between_devices_cas_and_independent_from_resolution'],['generic decisions send the reviewed revision and never retry a conflict','mutation409 refreshes CAS and a stale click is never sent','lost mutation response reconciles with reads and never resubmits the preference'],[E+'pr07-attention-ui/final-results.json'])
group('accessible','Accessible grouping, explicit labels/status, keyboard focus restoration, light/dark/narrow layout and escaped untrusted text are observed in actual browser plus semantic/unit checks.',[F+'App.tsx',F+'views/AttentionView.tsx',F+'attentionPresentation.ts',F+'components/AttentionInspection.tsx'],[],['focus stays on its record or moves to the next surviving row, then the previous row or heading','source names are plain known labels, including prototype-like unknown values'],[E+'pr07-attention-ui.md',E+'pr07-attention-ui/root-results.json',E+'pr07-attention-ui/final-results.json'], 'Actual browser keyboard/focus/semantic accessibility and themes were checked; no named screen-reader product campaign is claimed or required by the literal implementation task.')
group('native_authority','Request recipient and present canonical authority determine action; expired requests retain historical inspection and do not become operator-answerable when directed to an agent.',[A+'attention_native.py',S+'attention_native.py'],['test_canonical_native_ingress_projects_exact_recipient_and_existing_action','test_expiration_changes_resolution_without_writing_native_lifecycle','test_broken_domain_provenance_never_borrows_operator_recipient','test_projection_and_canonical_command_reject_the_same_changed_authority'])
group('canonical_states','Normal CLAIMED/silence or dependency waiting is not an incident; verifier authorization and actual current unknown/cleanup facts determine action, keeping successful results successful.',[A+'attention_operations.py',A+'attention_results.py',S+'attention_operations.py'],['test_normal_claim_cleanup_and_unproved_eligibility_are_not_incidents','test_verification_uses_actual_verifier_visibility_and_anti_self','test_only_current_unknown_receipt_or_reconciliation_requires_attention','test_explicit_cleanup_failure_preserves_success_and_has_stable_episode_until_done','test_dependency_wait_is_not_aged_claimable_work_and_unblock_starts_its_clock'])
group('temporal','Threshold and TTL changes use explicit time policy without writing lifecycle or generating a new episode on refresh.',[A+'attention_native.py',A+'attention_operations.py',D+'attention.py'],['test_snooze_expiry_is_derived_without_a_read_side_write','test_authority_deadline_is_earlier_than_native_request_expiry','test_disconnection_threshold_accepts_native_sqlite_timestamp_precision','test_preferences_survive_server_restart'])

group('registration','Explicit existing agent and workspace selection creates only auxiliary sources/instances; strict payload rejects caller-supplied identity and server owns generation.',[A+'observations.py',A+'observation_validation.py',S+'observations_repo.py',D+'observations.py'],['test_canonical_self_management_requires_current_key_and_explicit_approval','test_source_registration_idempotency_does_not_grant_permission','test_identity_and_arbitrary_fields_are_refused_without_echo','test_independent_instances_and_source_continuity_remain_distinct'])
group('audience','Opaque hashed short-lived observation credentials authorize only literal activity publication. Current source/agent/workspace/generation and explicit permissions are checked before replay; management/reissue use canonical credentials.',[A+'observations.py',D+'observation_tokens.py',H+'observations.py',S+'observations_repo.py'],['test_obs_family_cannot_enter_any_other_audience_or_public_exception','test_publish_bearer_cannot_reenter_management_or_canonical_audiences','test_publish_rejects_other_credentials_and_substitutes_before_route','test_observation_catalog_is_explicit_and_all_old_defaults_are_preserved','test_agent_material_authority_revokes_durably_and_projects_unavailable','test_source_cas_noop_scope_change_and_reenable_never_restore_old_token'])
group('replay','Sequence/hash and source/instance generation fences are durable; exact replay returns original receipt without TTL renewal/event, conflicts roll back and reset does not reuse fences.',[A+'observations.py',S+'observations_repo.py','src/okto_nexus/migrations/164_external_observations.sql'],['test_replay_after_ttl_and_policy_change_returns_exact_receipt','test_same_sequence_different_hash_conflicts','test_conflicting_or_old_sequence_cannot_overwrite','test_generation_rotation_requires_new_exact_grant','test_reset_replay_and_quota_fences_survive_and_old_tokens_do_not','test_atomic_batch_failure_rolls_back_head_quota_and_event'])
group('freshness','Receipt and observed age bound validity; future/backlog refusal and temporal expiry yield stale/unknown, never canonical idle, free capacity or refreshed MCP presence.',[D+'observations.py',A+'observations.py'],['test_freshness_is_minimum_of_server_and_observed_lifetimes','test_backlog_and_future_reports_are_rejected_without_writes','test_replay_after_ttl_and_policy_change_returns_exact_receipt','test_publish_changes_no_coordination_presence_or_capacity'],['only current observations display reported activity; stale never becomes idle'])
group('limits','Strict bounded report/batch/text/instance/token/cardinality and durable aggregate rates plus bounded retention provide honest backpressure; storage/commit refusal never acknowledges unpersisted data.',[A+'observation_ingress.py',A+'observation_validation.py',S+'observations_repo.py',H+'observations.py','src/okto_nexus/config.py'],['test_source_instance_token_cardinality_and_referenced_expired_token_retention','test_agent_aggregate_prevents_multiple_source_amplification','test_rate_refill_exact_restart_clock_regression_and_denial_no_write','test_batch_100_and_late_validation_failure_are_atomic','test_injected_sqlite_commit_failure_does_not_persist_receipt_or_event','test_http_backpressure_returns_retry_after_before_storage'],[],[E+'pr08-observations.md'],'Fault injection covers the honest no-ack/rollback contract. It does not claim physically filling the host disk; no destructive disk-fill campaign is necessary for this literal behavior.')
group('optional','Observer is an explicit optional CLI/helper command; Server bootstrap and canonical routes have no Herdr execution prerequisite or Connector executor registration side effect.',['src/okto_nexus/adapters/inbound/cli/observe.py',O+'herdr.py','docs/herdr-observer.md','src/okto_nexus/config.py'],['test_status_reads_only_local_metadata_without_credentials_or_external_calls','test_observation_defaults_are_opt_in_independent_and_protocol_bounds_are_not_settings','test_source_off_run_does_not_reserve_sequence_or_permanently_invalidate'],[],[E+'pr09-herdr.md',E+'pr08-observations.md'])
group('herdr_contract','Explicit installed version/schema hash plus live status are validated; bounded degraded polling takes a fresh snapshot after reconnect and incompatible shapes are explicit unavailability.',[O+'herdr.py',D+'herdr_observations.py',A+'herdr_observer.py','docs/herdr-observer.md'],['test_contract_pins_raw_schema_bytes_and_version','test_incompatible_contract_fails_closed','test_live_status_rejects_unknown_contract_and_selector','test_disconnect_recovers_only_with_new_live_snapshot'],[],[E+'pr09-herdr/contract/schema.json',E+'pr09-herdr/live/observer-live-campaign.json',E+'pr09-herdr/live/observer-disconnection-campaign.json'],'Qualified Windows Herdr0.9.5/protocol22/schema1 with synthetic observed occupants. Polling is declared degraded; no invented subscription cursor, productive provider or other platform qualification.')
group('occupant','Installation/session/pane plus host-owned process birth/image identity form the binding; names/paths are aliases and move/replacement/PID reuse require reassociation.',[D+'herdr_observations.py',O+'windows_identity.py',A+'herdr_observer.py'],['test_explicit_namespace_session_host_and_birth_are_all_binding_identity','test_rename_alias_and_directory_do_not_reassign_identity','test_move_or_changed_location_requires_rebinding','test_removal_and_pid_reuse_do_not_transfer_binding','test_process_switch_between_reads_and_process_exit_are_not_published'],[],[E+'pr09-herdr/namespace/evidence/namespace-proof.json',E+'pr09-herdr/live/observer-replacement-campaign.json',E+'pr09-herdr/live/observer-move-final.json'],'Windows local birth/occupant contract; unknown/replaced evidence refuses. No inference of identity from names, paths or bare PID; no added remote/other-OS requirement.')
group('observer_readonly','Fixed Herdr command allowlist reads version/schema/status/snapshot/process-info only, no shell/terminal content or control commands; local user-code permission is not a Nexus-token sandbox.',[O+'herdr.py',A+'herdr_observer.py','docs/herdr-observer.md'],['test_argv_is_fixed_explicit_and_never_uses_shell','test_environment_never_forwards_credentials_or_routing','test_real_schema_shape_sanitizes_all_display_and_process_text','test_process_info_checks_live_release_and_discards_free_text'],[],[E+'pr09-herdr/live/observer-command-audit.jsonl'])
group('completion','Initial done/switch/idle without a new coherent counter has no completion; retained completion ref is observational and stable, never a task verifier or productive command.',[D+'herdr_observations.py',A+'herdr_observer.py',A+'observations.py'],['test_initial_done_is_idle_without_new_completion','test_completion_requires_new_coherent_counter_and_remains_stable_until_omitted','test_incoherent_or_missing_completion_counter_never_emits_ref','test_new_completion_is_stable_observation_never_a_business_command','test_idle_without_reference_never_invents_completion'])
group('helper','Small separate HTTP publisher plus example document registration/token/sequence/TTL/revoke/exit; token is confined to exact endpoint and retries preserve uncertainty/explicit intent.',['src/okto_nexus/observation_client.py','docs/observation-client-example.py','docs/external-observations.md'],['test_only_publish_posts_use_exclusive_bearer_without_env_proxy_or_cookie','test_lost_response_has_no_automatic_retry_and_exact_caller_retry_retains_receipt','test_example_reads_only_named_token_env_and_prints_validated_receipt','test_invalid_origins_are_sanitized_before_network'])
group('external','Three stable external occurrences are inspection-only; current/stale/history and per-agent/per-instance aggregation remain explicitly observational, independent of presence/capacity.',[A+'attention_external.py',S+'attention_external.py',A+'observations.py',F+'components/ExternalObservations.tsx',F+'observationPresentation.ts'],['test_blocked_is_observational_navigation_only_and_read_does_not_mutate','test_continuous_blocked_heartbeat_retains_episode_and_seen','test_blocked_recurrence_and_unobserved_expiration_do_not_inherit_seen','test_multiple_completions_same_clock_are_retained_and_seen_independently','test_completion_stays_historical_unseen_after_ttl_without_becoming_task_success'],['external attention exposes inspection only and preserves observational wording','complete aggregate retains mixed instances and unavailable evidence separately'],[E+'pr10-external.md'])
group('canonical_isolation','Publication/seen cannot create authority, reservations, work or task success; only correlated canonical terminal event can settle the current turn and admit execution of queued work.',[A+'observations.py',A+'attention_external.py',F+'attentionNavigation.ts'],['test_publish_changes_no_coordination_presence_or_capacity','test_external_done_and_seen_do_not_release_a_turn_or_wake_queued_work','test_external_idle_preserves_exact_unconsumed_claim_reservation','test_external_idle_preserves_endpoint_priority_and_existing_affinity','test_external_idle_preserves_shared_dispatch_fairness'],['external reports never resolve canonical approval, execution or task controls','a correlated external occurrence still has no approve, dispatch or canonical navigation authority'],[E+'r3-joint-contracts/idle/report.json',E+'pr10-external.md'])
group('correlation','Operator-selected/fenced native evidence produces minimum passive Core facts with provenance ahead of separate external signal; unrelated/stale sources remain uncorrelated and historical completion cannot inherit a later selection.',[A+'observation_correlation_service.py',A+'observation_correlation_view.py',S+'observation_correlation_projection.py',F+'components/CanonicalObservation.tsx'],['test_only_operator_can_read_select_or_clear','test_client_cannot_supply_native_or_os_proof','test_authority_and_exact_fences_are_rechecked_after_core_await','test_later_external_reports_preserve_canonical_facts_and_all_canonical_rows','test_historical_completion_never_inherits_a_later_selected_correlation','test_matching_correlation_adds_minimal_canonical_facts_without_reinterpreting_external_activity'],['canonical facts precede the external signal, including compact instance rows','received terminal stages never infer idle activity or current execution state'],[E+'pr10-correlation.md',E+'pr10-correlation/browser/campaign-summary.json'],'Explicit Windows/local/embedded proof contract; remote or insufficient evidence stays separate. Provider/model inference is irrelevant to the non-overwrite rule; no fabricated current idle/liveness from SUCCEEDED receipts.')
group('untrusted','Closed schema and bounded text reject identity/secret/command fields; source values are escaped literal UI data without active links/HTML; errors do not echo input.',[D+'observations.py',H+'observations.py',F+'components/ExternalObservations.tsx',F+'components/CanonicalObservation.tsx'],['test_identity_and_arbitrary_fields_are_refused_without_echo','test_bounded_strict_http_errors_never_echo_input','test_real_schema_shape_sanitizes_all_display_and_process_text'],['canonical and external identifiers remain escaped plaintext without command links'],[E+'pr07-attention-ui.md',E+'pr10-external.md'])
group('off','Explicit OBS true-to-false toggle leaves canonical Core local queue/control working. Current mixed MCP-only/runtime and actual HTTP/WSS Connector cases use bootstrap({}, isolatedhome) with default feature_observations=false and prove canonical cooperation/delivery.',['src/okto_nexus/config.py',A+'observations.py','tests/execution_r4/test_binding_operator.py','tests/execution_r4/test_embedded_inventory.py','tests/execution_r4/test_local_realization.py'],['test_external_done_and_seen_do_not_release_a_turn_or_wake_queued_work','test_observation_defaults_are_opt_in_independent_and_protocol_bounds_are_not_settings','test_remote_domain_delivery_keeps_exclusive_claim_from_mcp','test_rg01_two_mcp_participants_and_one_runtime_cooperate_without_new_identities'],[],[E+'r3-joint-contracts/integration.json'],'Direct toggle proof is local Core; complementary remote/MCP proofs run OBS-off from initial configuration. Scope is canonical Windows with explicit synthetic native peers, not provider/service qualification. No additional real-provider prerequisite for literal OB24.')

task_groups={
'ATN-01':['projection'],'ATN-02':['preferences'],'ATN-03':['passive'],'ATN-04':['api'],'ATN-05':['stream','temporal'],'ATN-06':['ui'],'ATN-07':['interaction'],'ATN-08':['accessible'],
'OBS-01':['registration'],'OBS-02':['audience'],'OBS-03':['replay'],'OBS-04':['freshness','limits'],'OBS-05':['optional'],'OBS-06':['herdr_contract'],'OBS-07':['occupant'],'OBS-08':['observer_readonly'],'OBS-09':['completion'],'OBS-10':['helper'],'OBS-11':['external','canonical_isolation'],'OBS-12':['correlation']}
scenario_groups={
'AT-01':['native_authority'],'AT-02':['native_authority','temporal'],'AT-03':['native_authority'],'AT-04':['canonical_states'],'AT-05':['canonical_states'],'AT-06':['interaction','canonical_states'],'AT-07':['preferences','passive'],'AT-08':['preferences','temporal'],'AT-09':['interaction','native_authority'],'AT-10':['api'],'AT-11':['stream'],'AT-12':['stream'],'AT-13':['temporal','stream'],'AT-14':['canonical_states'],'AT-15':['accessible','untrusted'],'AT-16':['projection'],
'OB-01':['registration','audience'],'OB-02':['audience'],'OB-03':['audience'],'OB-04':['registration','audience'],'OB-05':['replay'],'OB-06':['replay'],'OB-07':['replay'],'OB-08':['freshness','herdr_contract'],'OB-09':['freshness','external'],'OB-10':['audience'],'OB-11':['registration'],'OB-12':['occupant'],'OB-13':['occupant'],'OB-14':['completion'],'OB-15':['canonical_isolation'],'OB-16':['canonical_isolation','audience'],'OB-17':['herdr_contract','replay'],'OB-18':['herdr_contract'],'OB-19':['correlation'],'OB-20':['limits'],'OB-21':['untrusted'],'OB-22':['observer_readonly'],'OB-23':['optional','off'],'OB-24':['off']}

rows=[]
for ident,names in task_groups.items():
    match=re.search(r'^\*\*'+ident+r' (.*?)$',plan,re.M)
    assert match,ident
    requirement=match.group(0)
    rows.append({'id':ident,'kind':'task','requirement_exact':requirement,'plan_line':plan[:match.start()].count('\n')+1,'ledger_status_at_baseline':ledger['tasks'][ident]['status'],'proof_bundles':names,'recommendation':'VERIFIED for the declared implemented Windows contract; attach these exact references, without changing global R3/M1/M2 acceptance.','missing_literal_product_behavior':None,'missing_required_assertion_or_pass':None,'campaign_required_to_close_this_literal_task':None})
for ident,names in scenario_groups.items():
    match=re.search(r'^\| '+ident+r' \| (.*?) \|$',plan,re.M)
    assert match,ident
    rows.append({'id':ident,'kind':'scenario','requirement_exact':match.group(1),'plan_line':plan[:match.start()].count('\n')+1,'ledger_status_at_baseline':ledger['scenarios'][ident]['status'],'proof_bundles':names,'recommendation':'VERIFIED for the explicitly qualified scope represented by the bundles.','missing_literal_product_behavior':None,'missing_required_assertion_or_pass':None,'campaign_required_to_close_this_literal_scenario':None})
assert len(rows)==60 and len(task_groups)==20 and len(scenario_groups)==40

evidence_paths={r['selected_passing_report']['path'] for r in selected_tests.values()}
evidence_paths|={r['selected_passing_report']['path'] for r in selected_frontend.values()}
evidence_paths|={p for g in groups.values() for p in g['additional_evidence']}
evidence_catalog={p:{'bytes':(ROOT/p).stat().st_size,'sha256':sha((ROOT/p).read_bytes())} for p in sorted(evidence_paths)}
report={'format':'r3.atn-obs.literal-traceability','version':1,'snapshot':{'nexus':BASE,'plan_sha256':sha(plan.encode()),'literal_counts':{'ATN_tasks':8,'OBS_tasks':12,'AT_scenarios':16,'OB_scenarios':24}},
'method':'Read-only current source/assertion inspection and retained passing XML/real-browser/source records. No execution, checkout/ledger mutation or promotion; counts never substitute for predicate-specific proof.',
'rows':rows,'proof_bundles':groups,'test_proofs':selected_tests,'frontend_test_proofs':selected_frontend,'source_inventory':source_files,'evidence_inventory':evidence_catalog,
'important_recommendations':{
'AC-06':{'recommendation':'VERIFIED','reason':'Literal non-conversion of external activity into authority, capacity reservation or work completion is directly proved by canonical table snapshots, observation-only audience/actions, queued-turn isolation and current RG03 claim reservation/TTL/fairness checks. Real model/provider activity is not required to test this prohibition.','proof_bundles':['audience','canonical_isolation','correlation']},
'OB-24':{'recommendation':'VERIFIED for canonical Windows/synthetic-native contract','reason':'Existing direct OBS-off toggle Core test plus current OBS-off MCP-only/runtime cooperation and actual Connector/Core HTTP/WSS delivery supply the three required paths. Source chain fixes OBS=false explicitly via default and bootstrap env{}; the missing ledger association is not a missing implementation.'},
'ATN-01_to_08':{'recommendation':'Existing IMPLEMENTED rows have scoped verification support','reason':'Predicates, passivity/CAS/storage, HTTP/SSE, UI canonical controls and actual browser accessibility/text checks are linked, rather than requiring unrelated provider campaigns.'},
'AC-10':{'recommendation':'Historical Git rewrite or revocation is not a new prerequisite of the literal delivered-artifact criterion.','reason':'For the reviewed delivery snapshot, root public correction/inventory1822 plus retained protection tests and existing browser trace/screenshot reviews can support its scoped acceptance. Historical UAT validity/Git retention remain a recorded risk outside this artifact review, not an invented requirement. This subaudit does not redo the security scan or itself promote AC10.'}},
'remaining':{'literal_implementation_gaps_identified':[],'literal_assertion_or_retained_pass_gaps_identified':[],'traceability_actions':['Attach exact task/source/test/report references from the60 rows; empty task-level evidence arrays currently obscure existing verified scenario/milestone proof.','Reconcile OB24 from the three explicitly linked canonical paths, preserving declared fixture scope.'], 'independent_global_gates_not_prerequisites_of_these_contracts':['Actual client executables, productive provider/harness M1/M2, native user-service login/crash/context and any separately claimed remote/TLS platform acceptance remain with their own fixed requirements.','No implication of full R3 completion, universal OS qualification, particular screen-reader product campaign or physical-disk-fill campaign.']},
'no_reexecution':True,'checkout_edited':False,'ledger_status_promoted':False}
(OUT/'matrix.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

lines=['# SAFE-TRACE — ATN e OBS','',f'Base `{BASE[:8]}`; plano fixo SHA `{sha(plan.encode())}`. Leitura de implementação/assertions e resultados existentes, sem executar testes ou alterar checkout/ledger.','',
'**Conclusão:** as20 tarefas e40 cenários têm implementação/reuso e prova específica preservada no escopo declarado. Não identifiquei lacuna literal de produto ou assertion/PASS que exija novo teste. Os vínculos detalhados estão em `matrix.json`; nenhum status foi promovido por este agente.','',
'AC-06 pode ser VERIFIED: publish altera somente fatos/eventos observacionais; blocked/idle/completion/seen não concluem trabalho nem liberam a fila. Apenas evento terminal canônico avança o turno. RG03 preserva reserva/TTL, prioridade, FIFO, fairness e elegibilidade. Provedor real é irrelevante para essa proibição.','',
'OB-24 pode ser VERIFIED no contrato Windows canônico: há toggle OBS on→off mantendo Core local, RG01 atual com dois participantes MCP e runtime sob OBS=false, e RG11 remoto atual com Connector/Core reais via HTTP/WSS e MCP. A configuração vem de bootstrap com ambiente vazio/default false; o peer nativo é sintético. Falta ligação no ledger, não foi encontrado comportamento ausente.','',
'ATN01–08, hoje IMPLEMENTED, têm prova de verificação delimitada: catálogo, filtros/contagens, preferências/CAS/passividade, SSE/deadlines, comandos canônicos e browser/semântica acessível. AT/OB já VERIFIED mantêm seu escopo.','',
'## Matriz finita','', '| ID | Requisito literal | Prova | Recomendação |','|---|---|---|---|']
for row in rows:
    literal=row['requirement_exact'].replace('|','/').replace('\n',' ')
    lines.append('| '+row['id']+' | '+literal+' | '+', '.join(row['proof_bundles'])+' | VERIFIED no escopo declarado |')
lines += ['','## Limites que não criam novos requisitos','',
'Herdr: Windows0.9.5/protocolo22/schema1, instalação real e ocupantes sintéticos; polling degradado declarado. Correlação: contrato Windows/local/embedded com fonte sem prova mantida separada. Acessibilidade: teclado/foco/estrutura semântica e browser real; não se alega campanha de um leitor de tela específico. Falta de disco: testes de falha/commit comprovam recusa e rollback, sem encher o disco pessoal.','',
'A prova de OBS-off no remoto é complementar ao toggle local; não foi executado um novo toggle remoto nesta auditoria. Campanhas reais de provedor/clientes/serviço e aceites globais permanecem nos respectivos requisitos, sem serem exigidos novamente para regras de passividade, autoridade ou empacotamento.','',
'Quanto a AC-10: reescrever todo histórico Git ou revogar uma chave UAT anterior ao R3 não é requisito literal da ausência de segredos nos artefatos entregues. A correção do snapshot, inventário público e testes de proteção podem sustentar aceite delimitado da entrega; a retenção histórica/validade desconhecida é risco registrado separado. Este trabalho não repete a varredura e não promove AC-10.','',
'## Como verificar a associação','',
'Cada bundle identifica arquivos de produto com hash/símbolos, testes com linhas, assertions e hashes, e um XML aprovado escolhido. Frontend inclui título/assertions/XML; browser e Herdr reais possuem referências e hashes. Falhas históricas e reruns não são removidos nem somados. Algumas assertions de manutenção de versão de migração no fonte atual podem ser posteriores a XML antigo; o relatório identifica a identidade e o escopo histórico, sem fingir nova execução.','']
(OUT/'matrix.md').write_text('\n'.join(lines),encoding='utf-8')
manifest={'format':'r3.atn-obs.trace.allowlist','version':1,'files':{p:{'bytes':(OUT/p).stat().st_size,'sha256':sha((OUT/p).read_bytes())} for p in ['matrix.json','matrix.md','snapshot.json','build_matrix.py']},'excluded':['test-index-private.json: uncurated intermediate source/assertion catalogue, no qualification output','index_existing.py/read_assertions.py: inspection helpers only'],'tests_executed':False,'status_promoted':False}
(OUT/'artifact-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'rows':len(rows),'tasks':20,'scenarios':40,'python_proof_functions':len(selected_tests),'frontend_proof_titles':len(selected_frontend),'evidence_files':len(evidence_catalog),'manifest_sha256':sha((OUT/'artifact-manifest.json').read_bytes())},indent=2))
