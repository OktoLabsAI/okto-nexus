"""Read-only curation of completed shard evidence; does not invoke pytest."""
import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
import xml.etree.ElementTree as ET

import psutil

HERE = Path(__file__).resolve().parent
RAW = Path(r'C:\Users\jpamb\AppData\Local\Temp\nexus-qc09-installed-shard3-_0m7o01m\qc09-installed-shard3')


def write(name, value):
    (HERE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def classify(node):
    if 'attention_results_upgrade' in node or 'coordination_requests' in node:
        return 'stale_migration_list_oracle_semantic_assertions_not_reached'
    if 'terminal_multi_harness' in node:
        return 'legacy_menu_assertion_or_scripted_input_incompatible_with_quick_connect_review'
    if 'renewal_reserves_observed_application_cost' in node:
        return 'test_calls_instance_method_with_None_self'
    if 'remote_failed_preparation' in node:
        return 'connector_fixture_child_AttributeError_service_generation_observed'
    if 'terminal_binding_approval' in node:
        return 'unprovided_interactive_input_under_pytest_capture'
    return 'observed_failure_unresolved_no_baseline_attribution'


def main():
    tests = list(ET.parse(RAW / 'tests.xml').iter('testcase'))
    failures = []
    for item in tests:
        failure = item.find('failure')
        if failure is not None:
            node = item.attrib['classname'] + '::' + item.attrib['name']
            failures.append(dict(node=node, classification=classify(node), time=item.attrib.get('time'),
                                 message=failure.attrib.get('message'), longrepr=failure.text))
    write('shard3-failures.json', failures)
    for name in ('campaign.json', 'tests.xml', 'origins-start.json', 'origins-finish.json',
                 'installed.json', 'effective-pytest-command.json', 'launcher-result.json', 'stderr.txt'):
        shutil.copyfile(RAW / name, HERE / ('shard3-' + name))
    # stdout remains preserved at RAW; hash/size below make that boundary explicit.
    me = psutil.Process()
    excluded = {os.getpid(), *(p.pid for p in me.parents())}
    matches = []
    for process in psutil.process_iter(['pid', 'ppid', 'create_time', 'exe', 'cmdline']):
        if process.pid in excluded:
            continue
        command = ' '.join(process.info['cmdline'] or [])
        if process.pid == 32508 or str(RAW.parent) in command:
            matches.append({key: process.info[key] for key in ('pid', 'ppid', 'create_time', 'exe')})
    write('shard3-process-absence.json', dict(observed_at=datetime.now(timezone.utc).isoformat(),
          marker=str(RAW.parent), recorded_child_pid=32508, observer_and_ancestors_excluded=True,
          matches=matches, own_campaign_processes_absent=not matches,
          limitation='Command marker and recorded CI child PID; not a machine-wide no-process claim.'))
    summary2 = json.loads((HERE / 'remainder2-stopped-summary.json').read_text())
    campaign = json.loads((RAW / 'campaign.json').read_text())
    write('qualification.json', dict(status='FAIL_INCOMPLETE_FULLSUITE_NOT_RELEASE_PASS',
          frozen_at=datetime.now(timezone.utc).isoformat(),
          wheel_sha256='01eb1ce064f62b09630c24b5ad339814b9e46c429a7c4e7ebf7561eae23cfff6',
          shard3=dict(status='FAIL_COMPLETED_NATURALLY', passed=1821, failed=36, skipped=54,
                      warnings=17, pytest_seconds=5271.40, exit_code=1,
                      changed_inputs=campaign.get('changed_inputs'), process_absent=not matches),
          shard2=dict(status='INTERRUPTED_HUNG_TEARDOWN_THEN_DERIVATIVE_STOPPED_AT_BOUNDARY',
                      original_pass_calls=145, original_failed_calls=3, derivative_failed_calls=3,
                      derivative_complete_passes=0, not_run=summary2['still_not_run_count'],
                      changed_inputs=summary2['changed_inputs_vs_original_start']),
          provenance='Parent pytest imports all three installed families with no bad origins. Some unchanged regression tests spawn explicit source-PYTHONPATH children; this is not an all-child installed qualification.',
          safety='Own temporary homes, sanitized environment, inert/fake test peers, no paid provider invocation. No product/test/CI/prefix changes by this curation.',
          limits=['No failures relabeled PASS.', 'No new tests or reruns after shard3 completion.',
                  'Migration tests fail before downstream semantic assertions.',
                  'Multi-harness scripted-input mismatch does not qualify its unexecuted recovery assertions.',
                  'No baseline attribution for unresolved failures without comparative evidence.']))
    pins = []
    for path in sorted(HERE.iterdir()):
        if path.is_file() and path.name != 'manifest-final.json':
            pins.append(dict(path=path.name, bytes=path.stat().st_size,
                             sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    path = RAW / 'stdout.txt'
    write('manifest-final.json', dict(files=pins, external_preserved_raw=[dict(path=str(path),
          bytes=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest())]))
    print(json.dumps(dict(shard3_failed=len(failures), cleanup_absent=not matches,
                          shard2_not_run=summary2['still_not_run_count'], manifest_files=len(pins))))


if __name__ == '__main__':
    main()
