"""Record exact R7 cuts without promoting untested literal scenarios."""
from datetime import UTC, datetime
import json
from pathlib import Path
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
LEDGER = HERE.parent / 'NEXUS_HOME_ESTADOS_LEDGER_R1.json'
SOURCE = '01b0de385398950ac4547aa8a5dcbc29473c12cb'


def read(relative):
    return json.loads((HERE / relative).read_text(encoding='utf-8'))


def main():
    source = read('source-tests/r7-home/qualification.json')
    suite = ET.parse(HERE / 'source-tests/r7-home/tests.xml').getroot().find('testsuite')
    assert suite is not None and int(suite.get('tests')) == 321
    assert all(int(suite.get(key, '0')) == 0 for key in ('failures', 'errors', 'skipped'))
    assert source['exit_code'] == 0 and source['process_exited']
    assert source['source_and_test_drift'] == []
    assert source['owned_command']['success']
    installed = read('package-hst-r7/installed-qualification.json')
    assert installed['source_commit'] == SOURCE
    assert installed['counts'] == dict(PASS=326, SKIP=0, FAIL=0, NOT_RUN=0)
    browser = read('browser-hst/cuts/r7-functional/qualification.json')
    assert browser['checks_pass'] == 21 and browser['checks_fail'] == 0
    assert browser['cleanup']['supervisor']['exit_code'] == 0
    assert not browser['cleanup']['own_root_processes']
    assert not browser['cleanup']['listener_pids']
    ready = read('package-hst-r7/READY.json')
    assert ready['ready'] and ready['source_commit'] == SOURCE and ready['prefix_frozen']
    assert ready['wheel_sha256'] == installed['wheel_sha256']
    ledger = json.loads(LEDGER.read_text(encoding='utf-8'))
    stamp = datetime.now(UTC).isoformat()

    def evidence(result, artifact, procedure, limitations):
        return dict(commit=SOURCE, timestamp=stamp, result=result,
            artifact_path='execution/' + artifact,
            command_or_procedure=procedure,
            environment='Windows; isolated R7 source or frozen installed wheel; synthetic peers; no provider or human',
            limitations=limitations)

    cuts = [
        evidence('PASS321 source-only; drift/timeout/force/remaining known processes0',
            'source-tests/r7-home/qualification.json',
            'Full selected Home source regression with exact XML and source/test guards',
            'Isolated dependencies with repository source imports. This is not the installed regression or browser.'),
        evidence('PASS326 actually installed; zero skip/fail/not-run',
            'package-hst-r7/installed-qualification.json',
            'One exact 326-node installed regression; copied test/helper guards and all module origins',
            'Selected Home regression plus original-recipient and private operator message/handoff cases. Counts do not qualify every complete ledger scenario, native adapter or operating system.'),
        evidence('PASS21 browser; zero failed checks, browser POST or provider invocation',
            'browser-hst/r7-functional-report.md',
            'Fresh installed Working/request/parallel-terminal/blocking/exact-context/partial-source/logout sequence',
            'Seen mutation not run. Unanswered request per-session close unconfirmed; application owner physical drain confirmed. No timing, native campaign, human, zoom or AT claim.'),
    ]

    def append_unique(items, entry):
        if not any(old.get('artifact_path') == entry['artifact_path']
                   and old.get('result') == entry['result'] for old in items):
            items.append(entry)

    for task in ledger['tasks']:
        if task['id'] in ('HST-005', 'HST-009', 'HST-010', 'HST-011', 'HST-012',
                          'HST-024', 'HST-025', 'HST-027', 'HST-028', 'HST-031', 'HST-032'):
            for entry in cuts:
                append_unique(task['evidence'], entry)
    for test in ledger['tests']:
        if test['id'] in ('HST-T-C03', 'HST-T-C04', 'HST-T-D09'):
            append_unique(test['evidence'], cuts[2])
        if test['id'] in ('HST-T-K01', 'HST-T-K04'):
            append_unique(test['evidence'], cuts[1])
    ledger['execution']['r7_validation'] = dict(
        source_commit=SOURCE, wheel_sha256=ready['wheel_sha256'],
        source_tests='PASS321', installed_tests='PASS326', browser_checks='PASS21',
        source='execution/source-tests/r7-home/qualification.json',
        installed='execution/package-hst-r7/installed-qualification.json',
        browser='execution/browser-hst/r7-functional-report.md',
        package_ready='execution/package-hst-r7/READY.json',
        performance='PENDING_EXCLUSIVE_R7_WINDOW', first_useful_dom='NOT_RUN',
        literal_scenario_promotions=0, default_rollout=False,
        human='DEFERRED_UNTIL_AUTOMATED_READINESS_REVIEW',
        schema_migration=False, core_connector_changes=False)
    ledger['execution']['r7_source'].update(
        installed='PASS326 on fresh frozen R7 prefix',
        browser='PASS21 scoped functional checks; performance remains separate')
    LEDGER.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(ledger['execution']['r7_validation']))


if __name__ == '__main__':
    main()
