"""Record pre-feature producer compatibility and its independent RO supplement."""
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
RELATIVE = 'remaining-qualification-r7-next/compat-batch/S4-old-producer-r9-reader'
cut = HERE / RELATIVE


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


for name, digest in read(cut / 'manifest.json').items():
    assert hashlib.sha256((cut / name).read_bytes()).hexdigest() == digest, name
q = read(cut / 'qualification.json')
assert q['status'] == 'PASS_K02_OLD_PRODUCER_R9_PROJECTION_WITH_POSTCUT_RO_PROFILE_SUPPLEMENT'
assert q['runner_exit_code'] == 0 and q['copy_count'] == 1 and q['copied_files'] == 21
assert q['source_guard_before'] == q['source_guard_after'] and not q['source_guard_after']['drift']
assert not q['current_Test_Finish_work_grant_created'] and q['provider_invocations'] == 0
assert q['physical_same_birth_remaining'] == 0 and not q['forced_containment']
assert len(q['actual_audited_ports']) == 2 and not q['listeners_after']
assert not q['cookie_token_auth_content_copied'] and not q['private_logs_copied']
assert all(phase['server_exit_code'] == 0 and phase['canonical_stop']['shutdown_outcome'] == 'drained'
           for phase in q['phases'])
protected = read(cut / 'protected-table-hashes.json')
assert len(protected['old_after_drained_stop']) == 8
assert all(value == protected['old_after_drained_stop'] for value in protected.values())
negotiation = read(cut / 'actual-negotiation-and-result-ids.json')
assert not negotiation['old']['home_versions_field_present']
assert negotiation['old']['result_ids'] == negotiation['current']['result_ids']
assert negotiation['old']['result_ids'] and negotiation['old']['server_id'] == negotiation['current']['server_id']
assert negotiation['current']['returned_presentation_version'] == 2
supplement = read(cut / 'profile-path-postcut-supplement.json')
assert supplement['status'] == 'PASS_READONLY_POSTCUT_SUPPLEMENT'
assert supplement['original_slash_predicate_selected'] == 0
assert supplement['selected_terminal_files'] == 5 and not supplement['data_modified']
assert not supplement['runtime_or_browser_started'] and not supplement['rerun']
assert all(row['at_single_copy_sha256'] == row['post_R9_stop_sha256'] for row in supplement['files'])
required = [row for row in supplement['files'] if row['required_profile_or_checkpoint']]
assert len(required) == 2 and all(row['bytes_after'] > 0 for row in required)
path = HERE.parent / 'NEXUS_HOME_ESTADOS_LEDGER_R1.json'
ledger = read(path)
entry = {
    'commit': q['new_artifact']['source_candidate'], 'timestamp': datetime.now(UTC).isoformat(),
    'artifact_path': 'execution/' + RELATIVE + '/qualification.json',
    'environment': 'Actual installed pre-feature0.3.6 producer and R9 reader in sequential isolated foreground services, canonical CLI/Core with inert protocol peer; one own-home copy after drained stop/physical absence',
    'command_or_procedure': 'Produce actual native question/decision/terminal result on old artifact; close/stop, copy21 files once byte-exact, authenticate same own account on R9 and query real negotiated Home/results; compare eight full-column typed-row hashes and exact result/Server IDs',
    'result': 'PASS K02: actual old capability field absent and R9 offers1/2, same nonempty result IDs/Server, eight protected tables unchanged through copy/start/read/stop, no new current Test/Finish/work/grant; both owners stopped/drained/physical0, real two-port audit empty, source/payload/tools unchanged. Independent posterior RO supplement confirms five terminal files including two nonempty profile/checkpoint documents against the captured at-copy map',
    'limitations': 'Original terminal/ path selector was vacuous on Windows and is not relabeled as executed; profile proof is a separate later read-only comparison. Old records were generated now by the actual pre-feature artifact, not backdated. Protected eight-table and selected-file scope, not whole-DB immutability after auth/bootstrap. New process instance/generation is expected for the copied temporary home; stored identities remain. No real provider, UI, human, Windows lifecycle or performance qualification.'}
test = next(test for test in ledger['tests'] if test['id'] == 'HST-T-K02')
test['status'] = 'PASS'
if not any(old.get('artifact_path') == entry['artifact_path'] for old in test['evidence']):
    test['evidence'].append(entry)
test['execution_notes'] = 'PASS actual pre-feature producer→one drained-state copy→R9 read, preserving native request/decision/result/receipt/grant hashes and IDs; independent posterior RO profile proof and original vacuous selector retained explicitly.'
ledger['execution']['r9_old_state_compatibility'] = {
    'status': 'PASS_K02_OLD_ARTIFACT_PRODUCER', 'qualification': entry['artifact_path'],
    'protected_tables': 8, 'copy_count': 1, 'files_equal_at_copy': 21,
    'profile_proof': 'INDEPENDENT_POSTCUT_RO; ORIGINAL_SELECTOR_VACUOUS',
    'current_productive_setup_or_work': False, 'provider_calls': 0,
    'canonical_stops': 'BOTH_DRAINED', 'physical_absence': True}
pending = ledger['execution']['local_usability_candidate']['pending_local_scopes']
pending[:] = [item for item in pending if item != 'old-producer state read compatibility']
path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'K02': 'PASS', 'copy_count': 1, 'profile_proof': 'POSTCUT_RO_NOT_ORIGINAL_PREDICATE'}))
