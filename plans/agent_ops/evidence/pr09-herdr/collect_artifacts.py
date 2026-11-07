"""Retain qualification artifacts, excluding all private credential files.

Run only after closing test reports. This does not run campaigns or declare
acceptance. --verify-only checks retained hashes without needing temporary data.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[3]
SECRET = re.compile(rb'nxobs_[0-9a-f]{64}|nxs_[A-Za-z0-9_-]{20,}')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def retained(source, relative, *, expected_sha=None):
    data = source.read_bytes()
    original = sha(data)
    if expected_sha is not None and original != expected_sha:
        raise AssertionError('Upstream artifact changed: ' + source.name)
    redactions = 0
    if source.suffix == '.xml':
        # Wrong-family synthetic credential strings in parametrized test IDs.
        # Original closed reports stay in Temp; their original hash is retained.
        data, redactions = SECRET.subn(b'[REDACTED_TEST_CREDENTIAL]', data)
    elif SECRET.search(data):
        raise AssertionError('Credential-shaped value in evidence allowlist: ' + source.name)
    target = ROOT / relative
    if not target.resolve().is_relative_to(ROOT.resolve()):
        raise AssertionError('Artifact target escaped evidence directory')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    record = dict(path=target.relative_to(REPO).as_posix(), bytes=len(data), sha256=sha(data),
                  original_sha256=original, synthetic_test_credential_redactions=redactions)
    if source.suffix == '.xml':
        cases = list(ET.fromstring(data).iter('testcase'))
        record.update(tests=len(cases), failures=sum(c.find('failure') is not None for c in cases),
            errors=sum(c.find('error') is not None for c in cases),
            skipped=sum(c.find('skipped') is not None for c in cases))
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--temp-root', type=Path)
    parser.add_argument('--installed-root', type=Path)
    parser.add_argument('--herdr-root', type=Path)
    parser.add_argument('--namespace-root', type=Path)
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    manifest_path = ROOT / 'artifact-manifest.json'
    if args.verify_only:
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        for item in manifest['artifacts']:
            if sha((REPO / item['path']).read_bytes()) != item['sha256']:
                raise AssertionError('Retained bytes changed: ' + item['path'])
        print(json.dumps(dict(verified_artifacts=len(manifest['artifacts']))))
        return
    if not all((args.temp_root, args.installed_root, args.herdr_root, args.namespace_root)):
        parser.error('Collection requires all four explicit qualification directories.')
    records = {}
    for source in sorted(args.temp_root.glob('pr09-*.xml')):
        record = retained(source, Path(source.name))
        records[record['path']] = record
    for label in ('qualified', 'qualified-v2'):
        upstream = args.installed_root / label / 'evidence-manifest.json'
        manifest = json.loads(upstream.read_text(encoding='utf-8'))
        for item in manifest['artifacts']:
            source = Path(item['path'])
            relative = source.relative_to(args.installed_root)
            if source.name.startswith('qualification-') and not source.name.endswith('.metadata.json'):
                raise AssertionError('Private qualification file requested by upstream manifest')
            record = retained(source, Path('installed') / relative, expected_sha=item['sha256'])
            prior = records.get(record['path'])
            if prior is not None and prior != record:
                raise AssertionError('Conflicting upstream evidence manifests')
            records[record['path']] = record
        record = retained(upstream, Path('installed') / label / upstream.name)
        records[record['path']] = record
    upstream = args.namespace_root / 'evidence/namespace-evidence-manifest.json'
    namespace = json.loads(upstream.read_text(encoding='utf-8'))
    assert namespace['result'] == 'passed' and namespace['nexus_published'] is False
    for item in namespace['artifacts']:
        source = Path(item['path'])
        relative = source.relative_to(args.namespace_root)
        record = retained(source, Path('namespace') / relative, expected_sha=item['sha256'])
        records[record['path']] = record
    record = retained(upstream, Path('namespace/evidence') / upstream.name)
    records[record['path']] = record
    for name in ('observer_entry.py', 'observer_live_campaign.py', 'observer_replacement_campaign.py',
                 'observer_reconnect_prepare.py', 'observer_disconnection_campaign.py',
                 'observer_event_proof.py', 'cleanup_campaign.py'):
        record = retained(args.installed_root / name, Path('installed/drivers') / name)
        records[record['path']] = record
    for name in ('pr09-herdr-fetch.py', 'pr09-herdr-contract.py', 'pr09-herdr-live.py',
                 'pr09-herdr-fixture-start.py', 'pr09-herdr-live-adapter.py',
                 'pr09-herdr-state-campaign.py', 'pr09-herdr-done-campaign.py'):
        record = retained(args.temp_root / name, Path('herdr-drivers') / name)
        records[record['path']] = record
    record = retained(args.herdr_root / 'work/Fixture.cs', Path('herdr-drivers/Fixture.cs'))
    records[record['path']] = record
    # Only explicit, non-secret live result/audit files. Credential files, state
    # journals and arbitrary stdout are never discovered by this collector.
    live_names = ('observer-live-campaign.json', 'observer-move-initial.json', 'observer-move-final.json',
        'observer-replacement-campaign.json', 'observer-expiry.json', 'observer-disconnection-campaign.json',
        'observer-command-audit.jsonl', 'observer-event-proof.json', 'observer-final-cleanup.json')
    for name in live_names:
        source = args.installed_root / 'qualified' / name
        if source.is_file():
            record = retained(source, Path('live') / name)
            records[record['path']] = record
    for name in ('state-campaign-with-done.json', 'namespace-campaign.json', 'cleanup.json'):
        source = args.herdr_root / 'live' / name
        if source.is_file():
            record = retained(source, Path('live') / name)
            records[record['path']] = record
    for source in sorted((ROOT / 'fixtures').glob('*.json')) + [ROOT / 'contract/schema.json']:
        record = retained(source, source.relative_to(ROOT))
        records[record['path']] = record
    selected = ['pr09-observer-move-final.xml', 'pr09-observation-client-final.xml',
                'pr09-herdr-model-windows-initial.xml', 'pr09-observation-journal-initial.xml',
                'pr09-observe-cli-final.xml']
    selected_records = [records[(ROOT / name).relative_to(REPO).as_posix()] for name in selected]
    assert sum(item['tests'] for item in selected_records) == 318
    assert not any(item['failures'] or item['errors'] or item['skipped'] for item in selected_records)
    artifact_list = sorted(records.values(), key=lambda value: value['path'])
    manifest = dict(schema_version=1, source_unique_tests=318, source_disjoint_reports=selected,
        additional_http_only_cli_regression_tests=2, combined_source_unique_tests=320,
        installed_v1_tests=319, installed_v2_tests=321, installed_reruns_not_added_to_source_unique=True,
        installed_v2_wheel_sha256='fe597e0e5a7256d6c3328382d4a046706cba3cc37f4e15e286afad54eab2d29d',
        credential_policy='Private bearer files excluded and never hashed; only credential-shaped synthetic parametrized test IDs are redacted from retained XML.',
        artifacts=artifact_list,
        aggregate_sha256=sha(json.dumps([(item['path'], item['sha256']) for item in artifact_list],
                                       separators=(',', ':')).encode()))
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    # Initial manifest remains a historical 316-test selection. Update only
    # retained-byte metadata where a synthetic test credential was redacted.
    initial_path = ROOT / 'initial-manifest.json'
    initial = json.loads(initial_path.read_text(encoding='utf-8'))
    for item in initial['reports']:
        final = records[item['path']]
        item.update(sha256=final['sha256'], original_sha256=final['original_sha256'],
                    synthetic_test_credential_redactions=final['synthetic_test_credential_redactions'])
    initial_path.write_text(json.dumps(initial, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(artifacts=len(artifact_list), source_unique_tests=318,
                         aggregate_sha256=manifest['aggregate_sha256'])))


if __name__ == '__main__':
    main()
