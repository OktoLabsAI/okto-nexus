"""Reconcile completed final installed cuts, retaining original failed cuts."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'NEXUS_QUICK_CONNECT_R1'
PACKAGE = BASE / 'execution/qc36-final-package'
FINAL = '9bc4034663ca63cfee43790b4bc03c38f8bdebcc'


def read(path):
    return json.loads(path.read_text('utf-8'))


def main():
    package = read(PACKAGE / 'qualification.json')
    assert package['source_candidate_commit'] == FINAL
    assert package['status'] == 'PASS_BUILD_INSTALL_SMOKE'
    wheel = package['artifacts']['okto_nexus-0.3.6-py3-none-any.whl']
    cuts, nodes, counts = [], {}, Counter()
    for name in ('installed-shard-0', 'installed-shard-1-final', 'installed-legacy'):
        folder = PACKAGE / name
        report = read(folder / 'qualification.json')
        assert report['status'] == 'PASS_SCOPED_INSTALLED', name
        assert report['source_candidate'] == FINAL
        assert report['exit_code'] == 0 and report['payload_files'] == 1028
        assert not report['source_drift'] and not report['payload_drift'] and not report['not_run']
        assert report['counts']['failed'] == report['counts']['errors'] == 0
        counts.update(report['counts'])
        for node in ET.parse(folder / 'evidence/tests.xml').findall('.//testcase'):
            identity = node.get('classname') + '::' + node.get('name')
            assert identity not in nodes, identity
            nodes[identity] = ('skipped' if node.find('skipped') is not None else
                               'failed' if node.find('failure') is not None or node.find('error') is not None else 'passed')
        cuts.append(dict(path=folder.relative_to(BASE).as_posix(), counts=report['counts'],
            sha256=hashlib.sha256((folder / 'qualification.json').read_bytes()).hexdigest()))
    assert len(nodes) == sum(counts.values())
    assert Counter(nodes.values()) == Counter({k: counts[k] for k in ('passed', 'skipped')})
    passed = {node for node, state in nodes.items() if state == 'passed'}
    cancel = [node for node in passed if '.test_qc35_review_cancel::' in node]
    render = [node for node in passed if '.test_quick_connect_render::' in node]
    assert len(cancel) == 8 and len(render) == 17
    assert sum('test_customize_cancel_and_review_eof_' in node for node in cancel) == 5
    assert sum('test_c02_g08_' in node for node in cancel) == 2
    assert sum('test_resume_eof_' in node for node in cancel) == 1
    legacy = read(PACKAGE / 'installed-legacy/qualification.json')
    assert legacy['counts']['passed'] == 3
    shell = read(PACKAGE / 'installed-shells/qualification.json')
    assert shell['status'] == 'PASS' and shell['mode'] == 'INSTALLED_HELPER_NO_CHECKOUT_IMPORT'
    assert shell['wheel_sha256'] == wheel and shell['payload_files'] == 1028 and not shell['payload_drift']
    original = read(PACKAGE / 'installed-shard-1/qualification.json')
    assert original['status'] == 'INCOMPLETE_OR_FAIL'
    git_antecedent = read(PACKAGE / 'installed-shard-1-counterpart/qualification.json')
    assert git_antecedent['status'] == 'INCOMPLETE_OR_FAIL'
    result = dict(status='PASS_SCOPED_INSTALLED', source_candidate=FINAL, wheel_sha256=wheel,
        counts=dict(counts), failures=counts['failed'], errors=counts['errors'], not_run=0,
        required_cancel_nodes_passed=len(cancel), required_render_nodes_passed=len(render),
        legacy_nodes_passed=3, qualifying_cuts=cuts,
        installed_shells='execution/qc36-final-package/installed-shells/qualification.json',
        exact_nodes=nodes,
        original_failed_cut=dict(path='execution/qc36-final-package/installed-shard-1/qualification.json',
            counts=original['counts'], not_run=len(original['not_run']),
            reason='Original runner created an empty Claude provider directory, contradicting the missing-home scenario. '
                   'Counterpart keeps every test byte unchanged and uses an explicitly nonexistent owned Claude path. '
                   'The original result remains failed/incomplete, not retrospectively green.'),
        git_failure_antecedent=dict(path='execution/qc36-final-package/installed-shard-1-counterpart/qualification.json',
            counts=git_antecedent['counts'], not_run=len(git_antecedent['not_run']),
            reason='A metadata-hint test observed a directory fallback instead of origin; '
                   'the earlier node passed and the failed cut did not record its reason. '
                   'No retrospective cause attribution. Final run records the public result without modifying it.'),
        limits=['Counts cover the three explicit qualifying cuts only; original failed/incomplete cuts are separate.',
            'Closed PIPE skips are literal skips; prior real console/WSL evidence is version-scoped separately.',
            'No provider/authentication, human/AT, universal platform or original broad-regression qualification.',
            'Parent application origins/payloads are guarded; nested-child provenance is limited to each unchanged test/proof.'])
    path = BASE / 'execution/final-installed-reconciliation.json'
    assert not path.exists(), 'Preserve published reconciliations; create a revision instead.'
    path.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(status=result['status'], counts=dict(counts),
        report=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())))


if __name__ == '__main__':
    main()
