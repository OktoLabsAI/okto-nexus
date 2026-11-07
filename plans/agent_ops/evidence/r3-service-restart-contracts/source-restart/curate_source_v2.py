"""Curate only explicitly named closed SVC-T23/T24 source artifacts."""
from pathlib import Path
import hashlib
import json
import re
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
REPO = Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
OUT = ROOT / 'public-v2'
EXPECTED_SOURCE = '76d063e78a2543e3e8234e035297539281e73f431578d29b8593740f19f6952a'
EXPECTED_XML = 'a1e42802f5646be68feb943cd477dac51a5d628a790c9a70c329fdbe8c9909c0'
PATTERNS = {
    name: re.compile(r'(?<![A-Za-z0-9_])' + name + r'[A-Za-z0-9_-]{20,}')
    for name in ('nxs_', 'nxobs_', 'ept_', 'nxl_')
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def dump(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def cases(data):
    found = []
    for case in ET.fromstring(data).iter('testcase'):
        status = next((name for name in ('failure', 'error', 'skipped')
                       if case.find(name) is not None), 'passed')
        found.append(dict(classname=case.get('classname'), name=case.get('name'),
                          status=status, seconds=float(case.get('time', '0'))))
    return found


def main():
    final = REPO / 'tests/execution_r4/test_service_restart_contracts.py'
    assert digest(final.read_bytes()) == EXPECTED_SOURCE
    assert digest((ROOT / 'canonical-owner-stdlib.source.py').read_bytes()) == EXPECTED_SOURCE
    assert digest((ROOT / 'canonical-owner-stdlib.xml').read_bytes()) == EXPECTED_XML
    assert not OUT.exists(), 'Do not overwrite a closed public collection'
    OUT.mkdir()
    artifacts = []

    def retain(source, relative, role):
        raw = source.read_bytes()
        text = raw.decode('utf-8')
        redactions = {}
        for prefix, pattern in PATTERNS.items():
            text, count = pattern.subn('[REDACTED_' + prefix.rstrip('_').upper() + ']', text)
            redactions[prefix] = count
        data = text.encode('utf-8')
        if source.suffix == '.xml':
            assert cases(raw) == cases(data), 'Redaction must preserve testcase identities/status'
        destination = OUT / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        record = dict(path=relative, role=role, source_path=str(source),
                      source_sha256=digest(raw), artifact_sha256=digest(data),
                      source_bytes=len(raw), artifact_bytes=len(data), redactions=redactions)
        artifacts.append(record)
        return record

    descriptions = {
        'initial': ('fixture_expectation_failure',
            'Expected synchronous refusal, but canonical intent admission precedes dispatch validation.'),
        'dispatch-final': ('fixture_expectation_failure',
            'Expired case expected a grant word in a deliberately generic denial; revoked observation deadline was shorter than real reconnect backoff plus jitter.'),
        'scope-final': ('fixture_cleanup_failure',
            'Contract assertions passed, but cleanup incorrectly used OperatorProfile outside its existing /api/v1 allowlist.'),
        'three-controls-explicit-origin': ('superseded_not_qualification',
            'Three passing records are invalid as restart qualification: Windows venv Popen PID could be a redirector, and death of the canonical owner was not proved.'),
        'canonical-owner': ('collection_error_no_child_started',
            'Temporary test dependency psutil was unavailable. Removed dependency; no environment mutation or product change.'),
        'canonical-owner-stdlib': ('final_qualification',
            'Canonical PID equals base-Python Popen PID; owned Windows HANDLE birth/parent and actual owner death are checked, followed by new generation and canonical drain/exit0.'),
    }
    attempts = []
    for stem, (classification, explanation) in descriptions.items():
        source = ROOT / (stem + '.xml')
        retained = retain(source, 'reports/' + source.name, classification)
        rows = cases(source.read_bytes())
        attempts.append(dict(report=retained['path'], raw_sha256=retained['source_sha256'],
            classification=classification, explanation=explanation, cases=rows,
            counts={kind: sum(row['status'] == kind for row in rows)
                    for kind in ('passed', 'failure', 'error', 'skipped')}))

    for name in ('scope-final.source.py', 'three-controls.source.py',
                 'three-controls-explicit-origin.source.py', 'canonical-owner.source.py',
                 'canonical-owner-stdlib.source.py'):
        retain(ROOT / name, 'source-snapshots/' + name, 'historical_test_source_snapshot')
    retain(final, 'final-source/test_service_restart_contracts.py', 'final_test_source')
    for name in ('command.json', 'dispatch-final-command.json', 'scope-final-command.json',
                 'three-controls-command.json', 'three-controls-explicit-origin-command.json',
                 'canonical-owner-command.json', 'canonical-owner-stdlib-command.json',
                 'interrupted-preparation.json', 'redirector-limitation.json', 'handle-probe.json'):
        retain(ROOT / name, 'preparation/' + name, 'preparation_metadata')
    for name in ('source-qualification.json', 'manifest.json'):
        retain(ROOT / name, 'superseded/' + name, 'superseded_report_not_current_qualification')

    owner_records = []
    owner_root = Path('C:/Users/jpamb/AppData/Local/Temp/pytest-of-jpamb/pytest-10715')
    for index, case in enumerate(('expired', 'revoked', 'valid')):
        path = owner_root / ('test_server_restart_preserves_' + str(index)) / 'owner-proofs.json'
        owners = json.loads(path.read_text(encoding='utf-8'))
        assert len(owners) == 2
        old, new = owners
        assert old['pid'] != new['pid'] and old['birth'] != new['birth']
        assert old['generation'] != new['generation']
        assert old['instance_id'] == new['instance_id']
        assert old['parent_pid'] == new['parent_pid'] == 8616
        assert old['state'] == 'crashed_owner_exited'
        assert new['state'] == 'canonically_drained_owner_exited'
        record = retain(path, 'owners/' + case + '.json', 'final_owned_process_proof')
        owner_records.append(dict(case=case, artifact=record['path'], owners=owners))

    command = json.loads((ROOT / 'canonical-owner-stdlib-command.json').read_text())
    environment = json.loads((ROOT / 'command.json').read_text())
    final_cases = attempts[-1]['cases']
    assert len(final_cases) == 3 and all(row['status'] == 'passed' for row in final_cases)
    qualification = dict(
        format='svc-t23-t24-source-qualification.v2', scope=['SVC-T23', 'SVC-T24'],
        supersedes='superseded/source-qualification.json',
        source=dict(path='tests/execution_r4/test_service_restart_contracts.py',
                    sha256=EXPECTED_SOURCE, unchanged_during_final_run=True),
        command=command['command'], environment=environment,
        child_import_contract='Base Python -I; dependency and product roots explicitly derived from qualification runner imports. The installed runner must therefore supply site-packages product roots.',
        final_unique_cases=3, final_counts=dict(passed=3, failed=0, errors=0, skipped=0),
        final_seconds=387.227, historical_xml_records=sum(len(row['cases']) for row in attempts),
        historical_failed_records=6, historical_collection_errors=1, superseded_passing_records=3,
        counts_note='Only the three final identities qualify. Repeated attempts and superseded passing records are not additional coverage; interrupted preparation has no XML and contributes zero cases.',
        attempts=attempts, owner_proofs=owner_records,
        assertions=[
            'Each Windows Server launch is tied to its own retained process HANDLE: canonical PID, FILETIME birth, direct parent, ServeLock generation and instance identity.',
            'The original canonical owner is proved dead before replacement; its durable dispatcher lease expires naturally. Replacement has new PID/birth/generation and the same installation instance_id.',
            'Same live Connector DaemonApp and real HTTP/WebSocket/local IPC/Core journals reconnect after Server loss. Native/provider behavior is synthetic.',
            'Installation, subject credential identity/permissions/limits, workspaces, bindings, profiles, Finish, executor IDs and completed operation/receipt history are retained.',
            'No additional probe, executor, opening or send is caused by reconnection; old work remains completed and its native session was explicitly closed before the crash.',
            'Expired and revoked grants remain typed as such and cannot dispatch native work: PERMISSION_DENIED, possible_effect false, native opens/sends 1/1 and used_executions 1.',
            'A valid-grant control admits only new explicit work on the same binding/executor with new operation/session IDs: native opens/sends 2/2 and used_executions 1 to 2.',
            'Each replacement is stopped via canonical CLI using the same home/loopback origin/product import paths; DRAINED, exit0 and HANDLE death are required.',
        ],
        history_limits=[
            'No immutable source snapshot was retained for initial and dispatch-final attempts; no fixture-source hash is claimed for those runs.',
            'The old three-passing-record report is retained verbatim but invalidated by redirector-limitation.json. It is not accepted as restart evidence.',
            'The interrupted preparation has no completed XML; whether cleanup stop ran is unknown, not inferred.',
        ],
        limits=[
            'Source qualification only; final installed qualification is parent-owned and pending at collection.',
            'Windows process HANDLE proof only; no claim for another operating system.',
            'No real provider, personal credentials/vault, physical second host or native service/task registration.',
            'Previous native session was closed before Server failure; active native-session survival is not claimed.',
            'Only a new test/helper file was changed; no product/ledger/docs/closed historical artifacts/commit/push changed by this task.',
            'Cleanup assertions prove the six owned Server processes exited. Private homes/databases and complete logs are excluded from this public collection.',
        ],
    )
    report = ROOT / 'source-qualification-v2.json'
    assert not report.exists()
    dump(report, qualification)
    retain(report, report.name, 'current_source_qualification')
    retain(Path(__file__), 'curate_source_v2.py', 'explicit_allowlist_collector')
    manifest = dict(format='svc-t23-t24-public-allowlist.v2', artifacts=artifacts,
        excluded=['private full logs', 'homes', 'databases', 'keys', 'unlisted paths'],
        transformations='UTF-8 decode/encode only; no newline normalization. Token-pattern replacements only if present. Every source and artifact SHA retained independently.',
        redaction_patterns={key: value.pattern for key, value in PATTERNS.items()},
        total_redactions=sum(sum(row['redactions'].values()) for row in artifacts),
        artifact_count=len(artifacts))
    dump(OUT / 'manifest.json', manifest)
    for record in artifacts:
        assert digest((OUT / record['path']).read_bytes()) == record['artifact_sha256']
    print(json.dumps(dict(public=str(OUT), artifacts=len(artifacts),
        total_redactions=manifest['total_redactions'],
        manifest_sha256=digest((OUT / 'manifest.json').read_bytes()),
        qualification_sha256=digest(report.read_bytes()), final_xml_sha256=EXPECTED_XML)))


if __name__ == '__main__':
    main()
