"""Curate closed RG-04 reports only. Never include homes, DBs or raw logs."""
from pathlib import Path
import hashlib
import json
import re
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    process = json.loads((ROOT / 'process-result.json').read_text(encoding='utf-8'))
    campaign = json.loads((ROOT / 'reports/campaign.json').read_text(encoding='utf-8'))
    assert campaign['status'] != 'RUNNING'
    original = (ROOT / 'reports/tests.xml').read_bytes()
    tree = ET.fromstring(original)
    cases = []
    for case in tree.iter('testcase'):
        status = next((tag for tag in ('failure', 'error', 'skipped') if case.find(tag) is not None), 'passed')
        cases.append({'identity': case.get('classname', '') + '::' + case.get('name', ''),
                      'status': status, 'seconds': float(case.get('time', '0'))})
    assert len(cases) == len({case['identity'] for case in cases})
    summary = {
        'scenario': 'RG-04', 'counts': {tag: sum(case['status'] == tag for case in cases)
                                      for tag in ('passed', 'failure', 'error', 'skipped')},
        'unique_cases': len(cases), 'cases': cases,
        'runner_exit_code': process['exit_code'],
        'runner_elapsed_seconds': process['elapsed_seconds'],
        'input_count': len(campaign['input_hashes']),
        'changed_inputs': campaign['changed_inputs'], 'campaign_status': campaign['status'],
        'claims': {'installed_artifacts_verified': True, 'synthetic_native_peers': True,
                   'real_provider_qualified': False, 'real_personal_credentials': False,
                   'native_windows_service_campaign': False, 'global_acceptance_promoted': False},
        'raw_xml_sha256': digest(original),
        'raw_log_sha256': digest((ROOT / 'stdout-private.log').read_bytes()),
    }
    (ROOT / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    public = ROOT / 'public'
    public.mkdir()
    selected = ['run.py', 'curate.py', 'selection.json', 'invocation.json', 'coverage-map.json',
                'process-result.json', 'summary.json', 'reports/installed.json',
                'reports/campaign.json', 'reports/tests.xml', 'prepare.py', 'finalize.py',
                'fixture.patch', 'fixture-adaptation.json', 'input-stability.json',
                'qualification.json']
    patterns = [
        ('synthetic_nexus_key', re.compile(rb'(?<![A-Za-z0-9_])nxs_[A-Za-z0-9_-]{32,}')),
        ('synthetic_observation_token', re.compile(rb'(?<![A-Za-z0-9_])nxobs_[A-Za-z0-9_.-]{32,}')),
    ]
    artifacts = []
    for name in selected:
        source = ROOT / name
        raw = source.read_bytes()
        curated = raw
        removed = {}
        for label, pattern in patterns:
            curated, count = pattern.subn(b'[REDACTED_' + label.encode('ascii') + b']', curated)
            if count:
                removed[label] = count
        if name.endswith('.xml'):
            parsed = ET.fromstring(curated)
            assert len(list(parsed.iter('testcase'))) == len(cases)
        dest = public / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(curated)
        artifacts.append({'path': name, 'source_path': str(source),
                          'original_sha256': digest(raw), 'artifact_sha256': digest(curated),
                          'bytes': len(curated), 'redactions': removed})
    manifest = {'format': 'r3-rg04-curated-evidence-v1', 'artifacts': artifacts,
                'aggregate_sha256': digest(json.dumps(artifacts, sort_keys=True, separators=(',', ':')).encode()),
                'raw_logs_and_test_homes_excluded': True,
                'historical_artifacts_modified': False}
    (public / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'public': str(public), 'counts': summary['counts'],
                      'unique_cases': len(cases), 'changed_inputs': summary['changed_inputs'],
                      'artifact_count': len(artifacts),
                      'redactions': sum(sum(item['redactions'].values()) for item in artifacts),
                      'manifest_sha256': digest((public / 'manifest.json').read_bytes())}))


if __name__ == '__main__':
    main()
