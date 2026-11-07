"""Read-only completion audit; writes only beside this file. No test execution."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
from datetime import datetime, timezone
import zipfile

OUT = Path(__file__).resolve().parent
ROOT = Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
REV = '26e6c746'
EXPECTED_PLAN = '20d0fafdedc793b97a277f5d41355d7d597ff724a77687394215eea3113ba996'
PLAN_PATH = 'PLANO_CODEX_NEXUS_INTEGRACAO_ATENCAO_ONBOARDING.md'
LEDGER_PATH = 'plans/agent_ops/ledger.json'

def git(*args: str) -> bytes:
    return subprocess.check_output(['rtk', 'proxy', 'git', *args], cwd=ROOT)

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def read_json(path: str):
    return json.loads((ROOT / path).read_text(encoding='utf-8-sig'))

revision = git('rev-parse', REV).decode().strip()
plan_bytes = git('show', f'{revision}:{PLAN_PATH}')
ledger_bytes = git('show', f'{revision}:{LEDGER_PATH}')
plan = plan_bytes.decode('utf-8-sig')
ledger = json.loads(ledger_bytes)
assert sha(plan_bytes) == EXPECTED_PLAN == ledger['plan_sha256']
criteria_section = plan.split('# 17. Critérios de conclusão geral', 1)[1].split('# 18.', 1)[0]
requirements = {f'AC-{int(n):02d}': text.strip() for n, text in re.findall(r'^(\d+)\. (.+)$', criteria_section, re.M)}
requirements.update({key: text.strip() for key, text in re.findall(r'^\| (RG-\d+) \| (.+?) \|$', plan, re.M)})
assert len(requirements) == 28

evidence_paths = {
 'locks': 'pr01-locks.md',
 'launch_recovery': 'pr02-launch-recovery.md',
 'upgrade': 'pr02-upgrade.md',
 'passive_connector': 'pr02-connector-passive.md',
 'doctor': 'pr03-project-doctor.md',
 'terminal_work': 'pr03-terminal-work.md',
 'identity': 'pr03-terminal-identity.md',
 'policy': 'pr03-terminal-policy.md',
 'remote_preset': 'pr03-remote-preset.md',
 'preset_evolution': 'pr03-preset-evolution.md',
 'dashboard': 'pr03-project-dashboard.md',
 'participant_contract': 'pr04-participant-contract.md',
 'participant_import': 'pr04-participant-contract-import.json',
 'participant_launch': 'pr04-participant-launch.md',
 'participant_removal': 'pr04-participant-removal.md',
 'cooperation': 'pr04-cooperation.md',
 'coordination': 'pr05-coordination-cli.md',
 'attention_backend': 'pr06-attention.md',
 'attention_ui': 'pr07-attention-ui.md',
 'attention_browser_root': 'pr07-attention-ui/root-results.json',
 'attention_browser_final': 'pr07-attention-ui/final-results.json',
 'attention_installed': 'pr07-attention-ui-contracts-installed.xml',
 'observations': 'pr08-observations.md',
 'herdr': 'pr09-herdr.md',
 'external_attention': 'pr10-external.md',
 'correlation': 'pr10-correlation.md',
 'correlation_installed': 'pr10-correlation/candidate-v2/installed.xml',
 'ledger_reconciliation': 'pr10-ledger-reconciliation.md',
 'bootstrap': 'pr03-remote-bootstrap.md',
 'renewal': 'pr03-remote-renewal.md',
 'renewal_package': 'pr03-remote-renewal/candidate-v2/package-proof.json',
 'guide': 'pr04-participant-guide/milestone.md',
 'guide_package': 'pr04-participant-guide/installed/candidate-v1/package-proof.json',
 'guide_import_agents': 'pr04-participant-guide/installed/servers/agents/import-proof.json',
 'guide_import_onboarding': 'pr04-participant-guide/installed/servers/onboarding/import-proof.json',
}
evidence = {}
for key, name in evidence_paths.items():
    path = 'plans/agent_ops/evidence/' + name
    data = (ROOT / path).read_bytes()
    evidence[key] = {'path': path, 'sha256': sha(data), 'bytes': len(data), 'role': 'existing_closed_evidence', 'reexecuted': False}
for key, path in {
 'native_campaign': 'plans/agent_ops/campaigns/windows-user-service.md',
 'service_docs': 'docs/service-lifecycle.md',
 'coordination_docs': 'docs/terminal-coordination.md',
 'participant_docs': 'docs/terminal-participant.md',
}.items():
    data = (ROOT / path).read_bytes()
    evidence[key] = {'path': path, 'sha256': sha(data), 'bytes': len(data), 'role': 'existing_plan_or_documentation', 'reexecuted': False}

campaigns = [
 {'id': 'SAFE-PACK', 'class': 'safe_artifact_correction_and_qualification', 'priority': 1,
  'authorization': 'No provider, personal vault or native registered service required; root already assigned this work. This audit does not run it.',
  'action': 'Finish the assigned CI Connector artifact/pin correction to the published renewal payload; install the selected Nexus/Connector/Core wheels with their declared dependencies in a new isolated environment and retain pip check plus exact wheel/import proofs.',
  'acceptance': ['Connector CI wheel hash equals the reviewed renewal wheel, or an exactly evidenced replacement with the same source payload.', 'Core mcp>=1.30,<2 requirement is satisfied in the new environment; do not reuse DX04 browser environment as dependency-solve proof.', 'CI runner and copied targeted tests load only the selected noneditable packages; preserve failures and overlap counts.'],
  'owner_state': 'Latest root progress: exact new wheels installed and pip check passed; eight CI cases are running. This audit has not inspected that new report and keeps the correction pending final root closure.'},
 {'id': 'SAFE-TRACE', 'class': 'safe_read_only_review', 'priority': 2,
  'authorization': 'Read-only evidence/code/document review; no external authorization required.',
  'action': 'Bind the 59 task IDs, 132 scenario IDs, 28 invariants and these 28 closure rows to exact existing passing identities, package hashes and scoped limits. Reconcile superseded historical open statements without rewriting closed artifacts.',
  'acceptance': ['Every claimed implemented/reused mandatory task has an exact source/test/evidence reference.', 'Carry-forward claims compare actual relevant package bytes; do not sum repeated reports or label historical tests as current executions.', 'Current CLI/help/schema/doc contracts and all named NOT_RUN/skip reasons agree; no global promotion until mandatory campaigns pass.']},
 {'id': 'SAFE-RG', 'class': 'safe_targeted_synthetic_integration_if_uncovered', 'priority': 3,
  'authorization': 'Disposable SQLite/HTTP/MCP fixtures and explicit native doubles only. No real provider, personal credential or persistent OS service.',
  'action': 'First map existing reports. Only uncovered assertions justify a small joint fixture campaign: RG-01 two MCP principals plus managed runtime; RG-02 concurrent MCP/runtime broadcast claim; RG-03 idle versus priority/fairness/eligibility/reservations; RG-04 four isolation modes; RG-05 uncertain restart paths; RG-11 one identity across MCP/runtime.',
  'acceptance': ['One canonical broadcast winner and one logical delivery without channel fan-out.', 'Exact isolation keys/session separation for shared, per_sender, per_sender_session and one_shot.', 'OBS changes do not change scheduler ordering, claims, reservations or productive state.', 'Process/checkpoint recovery preserves exact IDs and does not replay unknown productive effects.', 'Label simulated peers explicitly; these contract results alone do not qualify real MCP binaries or productive M1.']},
 {'id': 'SAFE-COMPAT', 'class': 'safe_compatibility_review_then_targeted_contract', 'priority': 3,
  'authorization': 'Versioned disposable artifacts/protocol fixtures; no provider and no downgrade of a personal database.',
  'action': 'Define the actual supported old/new client-Server pairs from retained version/protocol contracts, document refusal/additive behavior, then exercise only pairs lacking authoritative evidence.',
  'acceptance': ['Both old-client/new-Server and new-client/old-Server expectations are explicit.', 'Missing receipt/correlation/capability support refuses before new productive effects or preserves uncertainty; no implicit fallback/reissue.', 'Fixture protocol coverage is distinguished from executing an old binary; no universal backwards-compatibility claim.']},
 {'id': 'SAFE-PUBLIC-REVIEW', 'class': 'safe_allowlisted_artifact_review', 'priority': 2,
  'authorization': 'Review only public campaign/export artifacts and synthetic redaction fixtures; never enumerate or hash private vaults, bearer registries or personal databases.',
  'action': 'Close the public artifact allowlist, verify hashes and documented redactions, and compare exports/logs/examples/URLs against existing secret-handling tests. Check campaign homes/cleanup metadata and named skips.',
  'acceptance': ['No secret-bearing file is included in the public allowlist; known synthetic secret literals are absent or explicitly redacted.', 'Reports identify all executed versus NOT_RUN campaign scopes and initial failures.', 'Temporary scopes and owned-resource cleanup are recorded; absence of private-file collection is not mislabeled as a universal secret scan.']},
 {'id': 'REAL-M1', 'class': 'real_provider_campaign_pending_explicit_authorization', 'priority': 4,
  'authorization': 'Requires an explicitly selected provider/account, useful task, cost/effect scope and local/Connector execution environment. Setup consent alone does not authorize inference.',
  'action': 'On the selected installed package, accept the reviewed default project preset, perform authorized work, handle a representative native question/permission through terminal, obtain the correlated result and reopen the same work locally and via Connector.',
  'acceptance': ['No mandatory dashboard or keep-alive terminal; stable identity/configuration/requests.', 'Actual native model/context/permission behavior and scoped coordination are observed, with finite grants and no self-approval/admin expansion.', 'Record decisions, readiness/result time, provider/build/topology and continuity limitations; do not equate ready/idle with completion.']},
 {'id': 'REAL-SVC', 'class': 'native_service_campaign_pending_explicit_authorization', 'priority': 4,
  'authorization': 'Existing temporary-task request remains awaiting authorization. Its scope excludes logout/reboot/provider credentials and does not itself authorize the later login/crash/vault campaign.',
  'action': 'First execute only the immutable reviewed two-task Windows campaign if approved. Separately prepare explicit scopes for actual login, supervised crash/recovery, stop/removal and credential availability in the real service context needed by AC-13.',
  'acceptance': ['Task Scheduler observations agree with canonical owner/readiness/drain receipts for both components.', 'Actual login and crash recovery are demonstrated; XML validation or start via CLI is not login proof.', 'Selected credential backend/service context is validated without dumping secrets.', 'Owned tasks/processes are removed canonically; personal installation remains untouched; reboot/logout only if separately approved.']},
 {'id': 'REAL-MCP', 'class': 'two_real_client_chain_pending_explicit_authorization', 'priority': 4,
  'authorization': 'Requires approved disposable client configuration/credential namespaces and, if useful cooperation invokes models, explicit provider authorization. Prior parser/initialize fixtures do not authorize this campaign.',
  'action': 'Use the two explicitly versioned supported MCP clients with generated configuration and actual approved credential resolution, authenticate to canonical Nexus and demonstrate scoped participation/cooperation alongside managed runtime.',
  'acceptance': ['Two tested clients without new native adapters or duplicate canonical identities.', 'Canonical reply/handoff result provenance and exact workspace/peer/claim correlation; no prompt marker as proof.', 'Preserve single-delivery and broadcast exclusivity; record which client/build actually acted, not just identities sharing a key.', 'The existing synthetic responder initialize tests remain narrower historical evidence.']},
 {'id': 'REAL-REMOTE', 'class': 'remote_topology_TLS_vault_environment_pending', 'priority': 4,
  'authorization': 'Requires explicitly provided/approved hosts, origin/TLS deployment and credential backend; do not read personal credentials or create remote infrastructure implicitly.',
  'action': 'Qualify the chosen real remote deployment with the canonical agent credential only on the Connector host, explicit operator authority on its own client, current /me namespace/epoch and approved binding. Combine with REAL-M1 when authorized.',
  'acceptance': ['Remote availability never starts a local substitute Server or copies operator secrets.', 'Document actual host count, TLS and vault properties; loopback WSS does not qualify a two-physical-host deployment or a production TLS chain.', 'No new requirement that every valid deployment use two physical hosts/TLS: this closes those claimed deployment scopes only; AC-11 still requires its chosen local and Connector topologies.']},
 {'id': 'REAL-RECOVERY', 'class': 'real_interruption_campaign_pending_explicit_authorization', 'priority': 4,
  'authorization': 'Requires explicit interruption/network/suspend scope and, for active useful work, REAL-M1 provider authorization. No machine suspension/logout/reboot is implicit.',
  'action': 'In the approved local/remote execution context, interrupt connectivity/restart the owner and perform the specifically approved suspend/resume observation while an operation is active or uncertain; inspect original receipts before any new work.',
  'acceptance': ['Expired/revoked grants remain invalid; ownership/leases/claims are reconciled before admission.', 'No automatic productive replay, new identity, new request or grant renewal.', 'Record unrecoverable native-session continuity honestly and require explicit new-session work; do not promise recovery after unsupported power loss.']},
]

rows = []
def add(key, assessment, proven, missing, ev, nxt, note=''):
    old = ledger['completion_criteria' if key.startswith('AC-') else 'scenarios'][key]
    rows.append({'id': key, 'requirement_exact': requirements[key], 'ledger_status_at_snapshot': old['status'],
                 'assessment': assessment, 'proven_scope': proven, 'missing_authoritative_evidence': missing,
                 'evidence_ids': ev, 'next_campaigns': nxt, 'note': note, 'global_promotion': False})

add('AC-01','traceability_review_pending',
 ['Implementation/reuse and installed tests are recorded by milestone across SVC/DX/ATN/OBS; latest guide, remote bootstrap and renewal close several old implementation gaps.'],
 ['No criterion-level closure mapping for every mandatory task at the selected published payload; an empty AC evidence list is not proof that implementation is absent.'],
 ['ledger_reconciliation','guide','bootstrap','renewal','correlation'], ['SAFE-PACK','SAFE-TRACE'],
 'No new mandatory product behavior was identified in this audit; the concrete packaging gap is tracked in AC-07/RG-08.')
add('AC-02','combined_acceptance_pending',
 ['OBS is optional and independent; browser/HTTP/Core-dispatch fixtures show OBS/attention coexist without canonical writes. Individual SVC, DX and ATN contracts have installed evidence.'],
 ['One explicit combined closure record over the final coordinated package; prerequisite real M1/M2 gates remain open.'],
 ['herdr','external_attention','correlation','attention_ui','guide'], ['SAFE-PACK','SAFE-TRACE','SAFE-RG','REAL-M1','REAL-SVC','REAL-MCP'])
add('AC-03','real_client_chain_pending',
 ['Claude Code 2.1.317 and Codex 0.166.0 parsed generated configs and performed authenticated initialize/list against a synthetic responder in isolated protocol modes.'],
 ['Two actual clients participating/cooperating with canonical Nexus through the complete approved credential chain; responder and identity-only fixtures do not establish this.'],
 ['participant_contract','participant_launch','cooperation','guide'], ['REAL-MCP'])
add('AC-04','criterion_supported_with_declared_scope',
 ['Real browser and installed HTTP/SQLite exercised canonical approval, question and handoff decisions; stale generic revision returned 409 and canonical handoff verdict reached COMPLETED.',
  'Seen/snooze left 32 compared canonical work tables unchanged; exact source controls and reviewed decision/claim revisions are reused. Attention API adds no productive command.',
  'Final browser regression confirmed native-question receipt/native reply and handoff/approval draft recovery; backend/navigation tests cover action families not individually seeded in the browser.'],
 ['No substantive missing evidence for the literal central-action/lifecycle criterion was found. Historical package evidence must not be relabeled as a full current-wheel rerun.'],
 ['attention_ui','attention_browser_root','attention_browser_final','attention_installed','attention_backend','external_attention','correlation'], ['SAFE-TRACE'],
 'Existing ledger VERIFIED is justified for AC-04 as written. Synthetic native peers limit provider/native-harness qualification, which belongs to AC-11/13, not a hidden prerequisite for this criterion. No status change is made.')
add('AC-05','contract_evidence_strong_global_path_mapping_pending',
 ['Canonical message/handoff request IDs, fixed replay windows, lost replies, failed checkpoint writes and actual process-death recovery are qualified.',
  'Remote setup/Finish and authorization issuance recover original receipts over actual loopback transports without duplicate creation or reissue.'],
 ['Explicit all-new-path/restart inventory and exact report mapping at the final artifact; no blanket exactly-once claim outside the documented receipt windows.'],
 ['coordination','cooperation','bootstrap','renewal','terminal_work'], ['SAFE-PACK','SAFE-TRACE','SAFE-RG'],
 'This contract criterion can progress with isolated faults and synthetic peers; real active-harness interruption remains a separate AC-14 gate.')
add('AC-06','scoped_contract_proven_mapping_pending',
 ['External reports project only watch/inspection; real HTTP/SQLite/Core dispatch tests show done/seen do not release the queued turn.',
  'Browser snapshots preserve canonical tables; explicit correlation displays committed facts without treating external idle/completion as authority or capacity.'],
 ['Explicit mapping covering every priority/fairness/eligibility/reservation assertion in RG-03; preserve the separation when deriving current joint acceptance.'],
 ['observations','herdr','external_attention','correlation','correlation_installed'], ['SAFE-TRACE','SAFE-RG'])
add('AC-07','concrete_artifact_and_dependency_gap',
 ['Prior Core pure-import audit recorded zero network/process/thread effects and zero non-code reads; installed boundaries and noneditable payload proofs exist.',
  'Renewal package independently qualifies Connector wheel a8cf1810... from the latest published implementation.'],
 ['Published CI manifest still pins Connector wheel 63d99d16... instead of renewal a8cf1810....',
  'DX04 browser import proofs report mcp 1.29.1 while vendored Core requires mcp>=1.30,<2; browser observations do not establish a valid dependency solve.',
  'Fresh isolated declared-requirement installation, pip check, corrected CI pin and final import/boundary evidence are pending the assigned correction.'],
 ['participant_import','renewal_package','guide_package','guide_import_agents','guide_import_onboarding','correlation_installed'], ['SAFE-PACK','SAFE-TRACE'],
 'Concrete correction is in progress with the root/frontend/reviewer. This is not an authorization-only blocker and not a request to rewrite historical browser evidence.')
add('AC-08','final_document_contract_review_pending',
 ['Milestones document canonical CLI, receipts, schemas, finite limits, rollback and narrower qualification; published DX04 guide generates public commands without setup effects.'],
 ['Final help/schema/doc comparison spanning the current three-package set and removal of misleading aggregate conclusions from superseded historical limitations.'],
 ['guide','participant_docs','coordination_docs','service_docs','bootstrap','renewal','preset_evolution'], ['SAFE-TRACE','SAFE-COMPAT'])
add('AC-09','reporting_review_pending',
 ['Closed reports preserve initial failures, overlaps, named skips and synthetic-versus-real limits; real Herdr, real HTTP/browser and native client protocol modes are explicitly distinguished.'],
 ['Final single inventory of all NOT_RUN cases and environmental/authorization causes, including new package/dependency qualification limits; no execution is required merely to document these honestly.'],
 ['guide','herdr','cooperation','coordination','renewal','preset_evolution'], ['SAFE-TRACE','SAFE-PUBLIC-REVIEW'])
add('AC-10','public_artifact_scope_review_pending',
 ['Metadata-only checkpoints/exports, protected key input and allowlisted evidence collection exclude private bearer/DB files; retained synthetic secret redactions are documented.',
  'DX04 browser guide uses public commands and no real vault/provider; native-launch campaign did not find its fixture key in campaign-owned files.'],
 ['One final allowlisted public-artifact/export/log/example/URL review tied to hashes; this audit does not claim an exhaustive or personal-machine secret scan.'],
 ['bootstrap','renewal','herdr','participant_launch','guide','coordination'], ['SAFE-PUBLIC-REVIEW','SAFE-TRACE'])
add('AC-11','real_M1_pending',
 ['Terminal send/watch/question/decision/result/recovery, project identity/preset and Connector setup/renewal have actual HTTP/SQLite/IPC transport evidence with synthetic native/provider behavior.'],
 ['Actual useful native-harness/provider cycle locally and via Connector, including decision, result, no mandatory dashboard/keep-alive terminal and re-entry to the same work.'],
 ['terminal_work','identity','policy','bootstrap','renewal'], ['SAFE-PACK','REAL-M1','REAL-SVC','REAL-REMOTE'])
add('AC-12','scoped_lifecycle_proven_final_mapping_pending',
 ['Real contender processes and installed three-concurrent-starter campaigns prove one owner, late-child rejection, reuse, restart and canonical drain in both hosts.',
  'Remote bootstrap/reuse retains exact Server/binding identity without local Server fallback; installed-supervisor refusal is tested.'],
 ['Final artifact carry-forward and exact remote/no-double-supervisor case mapping; actual registered-supervisor coexistence is part of REAL-SVC, not proven by injected task effects.'],
 ['locks','launch_recovery','passive_connector','bootstrap','renewal'], ['SAFE-PACK','SAFE-TRACE','REAL-SVC'])
add('AC-13','native_service_and_real_context_pending',
 ['Windows task definition/ownership/control contracts, validate-only XML and injected native effects are implemented; detached processes are real.'],
 ['Actual native install, login start, stop, supervised crash/recovery and removal with real execution-context credential access. The pending two-task plan alone explicitly excludes login/logout/crash/credential acceptance.'],
 ['native_campaign','launch_recovery','upgrade','service_docs'], ['REAL-SVC'],
 'No POSIX/platform expansion or boot-without-login requirement is introduced. Qualify only platforms declared supported.')
add('AC-14','real_interruption_acceptance_pending',
 ['Detached restart, receipt/process-death recovery, live Herdr disconnect/replacement and remote epoch/grant uncertainty contracts have narrower evidence.'],
 ['Actual service/native-work restart, approved suspend/resume and network interruption with authority/ownership/uncertainty checked; loopback and synthetic peers do not establish real provider continuity.'],
 ['launch_recovery','coordination','herdr','renewal'], ['SAFE-TRACE','SAFE-RG','REAL-RECOVERY'])
add('AC-15','scoped_control_contract_proven_final_mapping_pending',
 ['Installed real CLI/detached lifecycle and passive status/logs/default doctor preserve absent state, do not create vaults/start work, and expose uncertainty; upgrade/drain/foreground paths have historical evidence.'],
 ['Current coordinated artifact mapping of the control/passivity cases; registered-task control qualification remains within AC-13 and must not be silently inferred.'],
 ['passive_connector','doctor','launch_recovery','upgrade','service_docs'], ['SAFE-PACK','SAFE-TRACE'],
 'A broad provider rerun is not required to validate diagnostic passivity; only a missing/failing mapped assertion would justify a targeted isolated regression.')
add('AC-16','preset_contract_proven_useful_native_acceptance_pending',
 ['Persistent reviewed identity, generalist role, scoped coordination permissions, finite grants and operator-only decisions are implemented and tested; remote Finish commits the reviewed configuration.'],
 ['Actual effective native harness context/tools/permissions and useful scoped collaboration in the default local/remote flow, without admin authority or self-approval.'],
 ['identity','policy','remote_preset','bootstrap','renewal','cooperation'], ['REAL-M1','REAL-MCP'])
add('AC-17','preservation_contract_proven_full_terminal_use_pending',
 ['Optional preset evolution retains custom choices; ordinary reconnect does not reapply defaults; remote completed reuse after explicit key rotation preserves bootstrap/Finish/configuration.',
  'Real dashboard introduction/guide inspections do not create identity/binding/grants or reapply setup; installed upgrades preserve context/data.'],
 ['Final cross-artifact carry-forward and actual continued useful native terminal cycle after reconnect/update/interface reopen; historical contracts do not close M1.'],
 ['preset_evolution','dashboard','guide','upgrade','renewal'], ['SAFE-PACK','SAFE-TRACE','REAL-M1','REAL-RECOVERY'])

add('RG-01','joint_contract_not_explicitly_mapped',
 ['Canonical MCP coordination, identity-only peer replies and managed-runtime setup each have isolated transport/persistence evidence.'],
 ['One combined two-MCP-participant plus managed-runtime workspace scenario proving unique identities; no exact authoritative retained run was mapped here.'],
 ['cooperation','coordination','bootstrap'], ['SAFE-PACK','SAFE-TRACE','SAFE-RG'],
 'This integration contract can use explicit synthetic peers. The distinct real-two-client acceptance remains AC-03/REAL-MCP.')
add('RG-02','specific_joint_race_evidence_missing',
 ['Canonical claim/admission and coordination tests cover related concurrency; a default-start concurrent-claim test exists, but is not evidence of this exact mixed-channel broadcast race.'],
 ['Exact simultaneous MCP/runtime broadcast claim with one committed winner, no duplicate lease/reservation/result and retained loser refusal.'],
 ['coordination','cooperation'], ['SAFE-TRACE','SAFE-RG'])
add('RG-03','partial_assertions_proven_specific_scheduler_mapping_missing',
 ['Installed external-observation isolation cases for OBS on/off prove done/seen do not release a turn or wake queued work; canonical row fingerprints remain unchanged in OBS browser/load campaigns.'],
 ['Exact idle assertions for priority, fairness, eligibility and claim reservations over the relevant scheduler paths; generic no-work-completion is narrower.'],
 ['external_attention','correlation','correlation_installed'], ['SAFE-TRACE','SAFE-RG'])
add('RG-04','four_mode_behavior_mapping_missing',
 ['Prior one-shot claim/admission and configuration-mode validation cases are retained; canonical isolation behavior is reused.'],
 ['A retained behavior matrix exercising shared/per_sender/per_sender_session/one_shot together with the new paths; configuration parser acceptance alone is insufficient.'],
 ['coordination','terminal_work','remote_preset'], ['SAFE-TRACE','SAFE-RG'])
add('RG-05','recovery_path_union_mapping_pending',
 ['Real process death/console recovery, bootstrap response loss, authorization submitted uncertainty and observer reconnection preserve original metadata and reject replay.'],
 ['One finite inventory mapping every new productive entry/recovery path and its fault boundary to an existing retained result; do not infer all paths from one receipt suite.'],
 ['coordination','cooperation','bootstrap','renewal','herdr'], ['SAFE-PACK','SAFE-TRACE','SAFE-RG'],
 'Synthetic/native doubles suffice for the no-replay contract; real provider interruption is separately AC-14.')
add('RG-06','import_contract_supported_current_package_closure_pending',
 ['Core pure import/render audit recorded zero sockets/process/thread effects and zero non-code reads; installed tests enforce domain/application import boundaries.'],
 ['Tie these checks and prohibited application-dependency scans to the corrected final three-package environment, including valid declared dependencies.'],
 ['participant_import','participant_contract','correlation_installed','renewal_package'], ['SAFE-PACK','SAFE-TRACE'])
add('RG-07','explicit_version_pair_evidence_missing',
 ['CLI coordination documents refusal of absent receipt contract; service lifecycle diagnoses incompatibility; native work retains uncertainty for missing correlation.'],
 ['Explicit supported old/new pair table and evidence for both directions; additive API statements do not constitute a complete version-pair campaign.'],
 ['coordination_docs','service_docs','terminal_work'], ['SAFE-COMPAT'])
add('RG-08','concrete_CI_artifact_gap',
 ['Latest published Nexus guide wheel has 690 raw files equal across source/staging/wheel/installation, including UI; prior coordinated wheels include migrations/resources and use noneditable imports.'],
 ['CI Connector pin is stale relative to latest published source; final coordinated dependency-solve/import/resource proof is pending.'],
 ['guide_package','renewal_package','guide_import_agents','guide_import_onboarding'], ['SAFE-PACK','SAFE-TRACE'])
add('RG-09','scoped_isolation_supported_final_manifest_review_pending',
 ['Published campaigns use disposable homes/workspaces, synthetic fixtures and explicit public allowlists; real Herdr/browser servers have recorded canonical cleanup.'],
 ['Final campaign inventory/allowlist review and the corresponding isolation/cleanup evidence for future authorized campaigns.'],
 ['guide','bootstrap','renewal','herdr','correlation'], ['SAFE-PUBLIC-REVIEW','SAFE-TRACE'],
 'No personal configuration or credentials were accessed during this audit; historical claims are not extended to unexecuted campaigns.')
add('RG-10','criterion_supported_with_declared_scope',
 ['Actual Chrome/Playwright interaction against installed HTTP/SQLite exists for project introduction, attention decisions, external OBS/correlation and the latest published DX04 guide.',
  'The guide browser campaign records 22 checkpoints, unchanged canonical table/credential projections, zero console messages and canonical cleanup.'],
 ['No missing browser interaction evidence was identified for those delivered UI surfaces. Dependency-invalid DX04 environment cannot serve as a reproducible dependency solve; it does not erase actual browser observations.'],
 ['dashboard','attention_ui','attention_browser_final','external_attention','correlation','guide','guide_import_agents'], ['SAFE-PACK','SAFE-TRACE'],
 'Existing ledger VERIFIED was originally scoped to project introduction; later closed browser records extend coverage. This audit does not mutate ledger status or claim all UI tests ran on one current wheel.')
add('RG-11','specific_dual_channel_delivery_evidence_missing',
 ['Canonical coordination/delivery and managed-runtime origins have related tests; no complete exact same-agent MCP-plus-runtime delivery exclusion run was mapped here.'],
 ['One logical delivery for the same identity with MCP and managed runtime concurrently eligible, including loser/consumption state and no channel fan-out.',
  'Use the corrected CI Connector artifact so mixed-channel qualification actually exercises the current published host implementation.'],
 ['coordination','cooperation','renewal_package'], ['SAFE-PACK','SAFE-TRACE','SAFE-RG'],
 'A matching test name or unrelated multi-recipient fan-out case is not authoritative evidence for this scenario. The fixture campaign can run without a real provider.')

vendor_bytes = git('show', f'{revision}:vendor/ci/manifest.json')
vendor = json.loads(vendor_bytes)
renewal_package = read_json(evidence['renewal_package']['path'])
connector_sha = renewal_package['packages']['okto_nexus_connector']['wheel_sha256']
old_sha = next(x['sha256'] for x in vendor['artifacts'] if x['path'].startswith('vendor/ci/okto_nexus_connector-'))
core_path = ROOT / 'vendor/wheels/okto_nexus_connector_core-0.0.14-py3-none-any.whl'
with zipfile.ZipFile(core_path) as z:
    metadata = z.read(next(n for n in z.namelist() if n.endswith('.dist-info/METADATA'))).decode()
mcp_requirement = next(l.removeprefix('Requires-Dist: ') for l in metadata.splitlines() if l.startswith('Requires-Dist: mcp'))
def find_mcp(value):
    if isinstance(value, dict):
        if isinstance(value.get('mcp'), str):
            return value['mcp']
        for x in value.values():
            r = find_mcp(x)
            if r: return r
    if isinstance(value, list):
        for x in value:
            r = find_mcp(x)
            if r: return r
    return None
environment_mcp = {k: find_mcp(read_json(evidence[k]['path'])) for k in ['guide_import_agents','guide_import_onboarding']}
assert old_sha != connector_sha
assert mcp_requirement == 'mcp<2,>=1.30'
assert set(environment_mcp.values()) == {'1.29.1'}

audit = {
 'format': 'okto.r3.finite-completion-audit', 'version': 1,
 'created_at_utc': datetime.now(timezone.utc).isoformat(),
 'scope': 'Read-only audit of published R3; existing evidence read, no tests rerun and no product/ledger edits.',
 'publication_snapshot': {'nexus_commit': revision, 'connector_commit': 'fb3fff473ff246adcffa9e91573ac85f7a394170', 'core_commit': '5d31784362676e7231b5c612c458a4d8f4b5db4a',
                          'plan_path': PLAN_PATH, 'plan_sha256': sha(plan_bytes), 'ledger_path': LEDGER_PATH, 'ledger_sha256': sha(ledger_bytes)},
 'fixed_inventory': {'tasks': len(ledger['tasks']), 'scenarios': len(ledger['scenarios']), 'invariants': len(ledger['invariants']), 'completion_criteria': 17, 'joint_scenarios': 11},
 'actions_executed': {'tests': 0, 'providers': 0, 'service_starts': 0, 'credentials_accessed': 0, 'checkout_edits': 0, 'ledger_promotions': 0},
 'interpretation_rules': [
  'Exact requirement text comes from the immutable plan, avoiding legacy ledger encoding corruption.',
  'Evidence is authoritative only for its actual artifact/platform/fixture and assertions; historical scopes are not current reruns.',
  'No test counts are summed across overlapping reports; file-name/test-name search alone is not proof of a full scenario.',
  'Existing VERIFIED is assessed for the literal criterion, not silently expanded into global R3 or real-provider acceptance.',
  'SAFE campaigns are next scoped work proposals, not work executed by this audit; map retained evidence before adding or rerunning tests.',
  'No automatic adoption of externally edited service definitions, new platforms, new SLO, global authority system or other product requirement is introduced.',
  'TLS/two physical hosts are explicit unqualified deployment scopes, not invented requirements for every valid local/Connector installation.',
 ],
 'findings': [
  {'id': 'F-01', 'type': 'concrete_artifact_gap', 'rows': ['AC-07','RG-08','RG-11'], 'source': f'{revision}:vendor/ci/manifest.json', 'source_sha256': sha(vendor_bytes), 'published_ci_connector_sha256': old_sha, 'qualified_renewal_connector_sha256': connector_sha, 'state': 'Assigned correction in progress; not accepted here.'},
  {'id': 'F-02', 'type': 'dependency_qualification_gap', 'rows': ['AC-07','RG-06','RG-08','RG-10'], 'core_wheel_sha256': sha(core_path.read_bytes()), 'core_requires_mcp': mcp_requirement, 'guide_environment_mcp': environment_mcp, 'state': 'Fresh declared-dependency solve/pip check pending; preserve historical browser observations separately.'},
  {'id': 'F-03', 'type': 'evidence_mapping_gap', 'rows': ['RG-01','RG-02','RG-03','RG-04','RG-05','RG-07','RG-11'], 'state': 'Safe evidence review and only specifically uncovered synthetic/compatibility checks can progress independently of provider/native-service authorization.'},
  {'id': 'F-04', 'type': 'existing_verified_scope_supported', 'rows': ['AC-04','RG-10'], 'state': 'Existing canonical browser/backend evidence supports the literal criteria within recorded artifact scope; no global promotion.'},
 ],
 'criteria': rows, 'campaigns': campaigns, 'evidence_catalog': evidence,
 'parallel_progress_not_independently_reviewed': 'After the published snapshot, root reported exact new-wheel pip check passed and eight CI cases running. SAFE-PACK remains pending final root closure; this audit preserves the published mismatch and does not claim that the new qualification has failed or has not started.',
 'global_conclusion': 'R3 remains incomplete. Authorization is not the sole remaining dependency: the CI Connector pin and dependency-solve gaps are concrete, and finite evidence/compatibility/joint-contract reviews can proceed safely. Real provider/native-service/two-client and claimed remote-deployment/recovery scopes remain separately gated. No other mandatory missing product behavior was established by this read-only audit.',
}
assert audit['fixed_inventory'] == {'tasks':59,'scenarios':132,'invariants':28,'completion_criteria':17,'joint_scenarios':11}
assert {r['id'] for r in rows} == set(requirements)
assert len(rows) == 28
known_campaigns = {c['id'] for c in campaigns}
for row in rows:
    assert row['requirement_exact'] == requirements[row['id']]
    assert set(row['evidence_ids']) <= set(evidence)
    assert set(row['next_campaigns']) <= known_campaigns

json_path = OUT / 'completion-matrix.json'
json_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

lines = [
 '# Auditoria finita de conclusão R3', '',
 f'Snapshot publicado: Nexus `{revision}`, Connector `fb3fff473ff246adcffa9e91573ac85f7a394170`, Core `5d31784362676e7231b5c612c458a4d8f4b5db4a`.', '',
 f'Plano fixo: `{EXPECTED_PLAN}`. A matriz preserva exatamente 17 critérios e 11 cenários RG; não altera estados do ledger. Nenhum teste, provedor, serviço ou credencial foi executado/acessado.', '',
 '**Conclusão:** R3 permanece incompleto. Há duas pendências concretas e seguras de empacotamento/qualificação, além de campanhas reais e da reconciliação finita de evidências. Não é correto reduzir tudo a autorização pendente.', '',
 f'- O CI publicado usa Connector `{old_sha}`, enquanto a wheel de renovação qualificada é `{connector_sha}`. A correção está atribuída, mas não é declarada concluída aqui.',
 '- O Core declara `mcp>=1.30,<2`; os dois import proofs do browser DX04 registram `mcp==1.29.1`. As observações do browser permanecem válidas em seu ambiente histórico, mas não comprovam resolução válida das dependências. A nova venv deve usar requisitos declarados e `pip check`.',
 '- Progresso paralelo informado pelo root: instalação das wheels exatas e `pip check` passaram; oito casos CI estavam em execução. O relatório novo não foi inspecionado nesta auditoria. A correção permanece pendente apenas de fechamento pelo root, sem alterar retroativamente o snapshot publicado.',
 '- AC-04 está sustentado pelo seu critério literal: decisões canônicas reais no browser, CAS/revisões e ausência de lifecycle paralelo. Peer sintético limita o aceite do harness/provedor, não invalida esse critério da central. RG-10 também possui campanhas reais de browser/backend; nenhuma delas equivale a um rerun global no pacote atual.', '',
 '## Ordem de fechamento', '',
 '1. SAFE-PACK: encerrar a correção já atribuída de pin/artefato e resolver dependências em ambiente isolado.',
 '2. SAFE-TRACE e SAFE-PUBLIC-REVIEW: vincular critérios aos relatórios exatos, comparar payloads carregados, conferir docs/skips/allowlist e preservar limites históricos.',
 '3. SAFE-RG e SAFE-COMPAT: somente após mapear o existente, executar os casos conjuntos/pares de versões ainda sem prova exata. Fixtures explícitas permitem esse trabalho sem inferência ou serviço nativo registrado.',
 '4. REAL-M1, REAL-SVC, REAL-MCP, REAL-REMOTE e REAL-RECOVERY: preparar/aplicar apenas os escopos explicitamente autorizados. O plano de duas tarefas temporárias não inclui o aceite completo de login/crash/cofre nem autoriza inferência, logout ou reboot.', '',
 '## Matriz', '',
 'A redação integral de cada requisito, todas as lacunas e o critério de saída de cada campanha estão no JSON. Evidência histórica não é somada nem apresentada como nova execução.', '',
 '| ID | Escopo comprovado / limite restante | Próximo fechamento |',
 '|---|---|---|',
]
for row in rows:
    proven = row['proven_scope'][0].replace('|', '\\|')
    missing = row['missing_authoritative_evidence'][0].replace('|', '\\|')
    refs = ', '.join(row['evidence_ids'][:3])
    lines.append(f"| {row['id']} ({row['ledger_status_at_snapshot']}) | {proven} **Falta:** {missing} [{refs}] | {', '.join(row['next_campaigns'])} |")
lines.extend(['', '## Evidências citadas', '', 'Caminhos relativos à raiz Nexus; o JSON registra SHA-256 e tamanho de cada arquivo. Os artefatos originais não foram alterados.', ''])
for key, value in evidence.items():
    lines.append(f"- `{key}`: `{value['path']}`")
lines.extend(['', '## Limites da auditoria', '',
 'Não executa regressão, não prova ausência universal de defeitos e não promove tarefas. Um caso com nome semelhante não foi tratado como prova de RG-02/04/11. A leitura encontrou evidências mais amplas do que alguns campos AC/RG do ledger, mas essa reconciliação exige referência exata, não atualização automática.', '',
 'Não propõe adoção automática de definições de serviço alteradas, novas plataformas, SLOs ou APIs. TLS/dois hosts são escopos de implantação a qualificar quando declarados, não exigências inventadas para toda instalação válida.', '',
 'Os resultados futuros dos trabalhos paralelos devem produzir uma nova revisão desta matriz; este snapshot publicado e suas pendências não devem ser sobrescritos retroativamente.', ''])
md_path = OUT / 'completion-matrix.md'
md_path.write_text('\n'.join(lines), encoding='utf-8')

validation = {'format':'okto.r3.audit-validation','version':1,'plan_sha256':EXPECTED_PLAN,
              'exact_criterion_count':17,'exact_RG_count':11,'duplicate_ids':0,'unknown_evidence_refs':0,'unknown_campaign_refs':0,
              'all_requirements_equal_fixed_plan':True,'all_cited_files_exist':True,'tests_executed':0,'checkout_changes_by_audit':0,
              'new_product_requirements':False,'global_promotion':False}
(OUT / 'validation.json').write_text(json.dumps(validation,indent=2)+'\n',encoding='utf-8')
manifest = {'format':'okto.r3.audit-artifact-manifest','version':1,'published_nexus_commit':revision,'plan_sha256':EXPECTED_PLAN,
            'files':{p.name:{'sha256':sha(p.read_bytes()),'bytes':p.stat().st_size} for p in [Path(__file__),json_path,md_path,OUT/'validation.json']}}
(OUT / 'artifact-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'output':str(OUT),'rows':len(rows),'campaigns':len(campaigns),'evidence_files':len(evidence),
                  'matrix_sha256':sha(json_path.read_bytes()),'markdown_sha256':sha(md_path.read_bytes()),
                  'manifest_sha256':sha((OUT/'artifact-manifest.json').read_bytes())},indent=2))
