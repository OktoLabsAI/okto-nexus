"""Retain the explicit, completed PR08 source JUnits and deduplicate acceptance.

Run from any directory with Python 3.10+; defaults describe the original run.
Only the eighteen named source reports are collected. Later installed reports
belong to their own qualification and must not silently enter this selection.
Existing unrelated manifest keys are preserved for the installed collector.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET


REPORTS = {
    'pr08-observation-audience-initial.xml': 29,
    'pr08-observation-audience-wiring-final.xml': 10,
    'pr08-observation-http-corrected-fixture.xml': 11,
    'pr08-observation-http-final.xml': 12,
    'pr08-observation-http-initial.xml': 11,
    'pr08-observation-permissions-initial.xml': 48,
    'pr08-observation-retention-final.xml': 10,
    'pr08-observation-retention-initial.xml': 9,
    'pr08-observation-retention-regression-initial.xml': 29,
    'pr08-observation-service-final.xml': 24,
    'pr08-observation-service-initial.xml': 22,
    'pr08-observation-settings-initial.xml': 101,
    'pr08-observation-settings-regression-initial.xml': 77,
    'pr08-observation-structural-regression.xml': 21,
    'pr08-observations-domain-initial.xml': 135,
    'pr08-observations-storage-faults-concurrency.xml': 4,
    'pr08-observations-storage-final.xml': 39,
    'pr08-observations-storage-initial.xml': 33,
}

# Later entries take precedence for the same exact (classname, name). This
# chooses the final HTTP-wiring run as the provenance of its ten repeated cases.
SELECTED = [
    'pr08-observations-domain-initial.xml',
    'pr08-observation-permissions-initial.xml',
    'pr08-observation-settings-initial.xml',
    'pr08-observation-settings-regression-initial.xml',
    'pr08-observation-audience-initial.xml',
    'pr08-observation-audience-wiring-final.xml',
    'pr08-observation-service-final.xml',
    'pr08-observation-http-final.xml',
    'pr08-observations-storage-final.xml',
    'pr08-observation-retention-final.xml',
    'pr08-observation-retention-regression-initial.xml',
    'pr08-observation-structural-regression.xml',
]
DIAGNOSTICS = {
    'pr08-observation-http-initial.xml': (
        'fixture_failure',
        'All eleven cases failed during setup: SqliteAgentRepo.set_permissions() '
        'was called without its required keyword-only preset_id. This is retained '
        'diagnostic evidence, excluded from acceptance. The corrected fixture and '
        'final twelve-case run are both retained.'),
    'pr08-observation-http-corrected-fixture.xml': (
        'superseded_green_diagnostic', 'Eleven cases with the corrected fixture; superseded by the final twelve-case HTTP run.'),
    'pr08-observation-retention-initial.xml': (
        'superseded_green_diagnostic', 'Nine cases before the orphan-only rate-bucket cleanup correction; superseded by ten final cases.'),
    'pr08-observation-service-initial.xml': (
        'superseded_green_diagnostic', 'Initial twenty-two-case service run; superseded by twenty-four final cases.'),
    'pr08-observations-storage-initial.xml': (
        'superseded_green_diagnostic', 'Initial thirty-three-case storage run before the final rate-retention correction.'),
    'pr08-observations-storage-faults-concurrency.xml': (
        'superseded_green_diagnostic', 'Four additional fault/concurrency cases; all included in the final thirty-nine-case storage run.'),
}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def parse_report(data, name):
    root = ET.fromstring(data)
    cases = list(root.iter('testcase'))
    suites = [suite for suite in root.iter('testsuite') if not list(suite.iter('testsuite'))[1:]]
    identities = [(case.get('classname', ''), case.get('name', '')) for case in cases]
    if len(set(identities)) != len(identities):
        raise ValueError(f'Duplicate case identities within {name}')
    totals = dict(tests=len(cases), failures=sum(case.find('failure') is not None for case in cases),
                  errors=sum(case.find('error') is not None for case in cases),
                  skipped=sum(case.find('skipped') is not None for case in cases))
    for field, actual in totals.items():
        declared = sum(int(suite.get(field, 0)) for suite in suites)
        if declared != actual:
            raise ValueError(f'JUnit {field} mismatch in {name}: {declared} != {actual}')
    if totals['tests'] != REPORTS[name]:
        raise ValueError(f'Unexpected completed case count in {name}')
    totals['duration_seconds'] = str(sum((Decimal(suite.get('time', '0')) for suite in suites), Decimal(0)))
    problems = [dict(classname=case.get('classname', ''), name=case.get('name', ''),
                     kind=child.tag, message=child.get('message', ''))
                for case in cases for child in case if child.tag in {'failure', 'error', 'skipped'}]
    return totals, identities, problems


def collect(temp_root, repo_root, verify_only):
    destination = repo_root / 'plans/agent_ops/evidence/pr08-observations'
    manifest_path = repo_root / 'plans/agent_ops/evidence/pr08-observations-tests.json'
    destination.mkdir(parents=True, exist_ok=True)
    reports, identities_by_report = [], {}
    for name in sorted(REPORTS):
        original = temp_root / name
        before = original.stat()
        data = original.read_bytes()
        after = original.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise RuntimeError(f'Report changed while collecting: {original}')
        totals, identities, problems = parse_report(data, name)
        selected = name in SELECTED
        if selected and any(totals[field] for field in ('failures', 'errors', 'skipped')):
            raise ValueError(f'Acceptance selection is not fully green: {name}')
        retained = destination / name
        if retained.exists():
            if retained.read_bytes() != data:
                raise ValueError(f'Refusing to overwrite different historical evidence: {retained}')
        elif verify_only:
            raise FileNotFoundError(retained)
        else:
            retained.write_bytes(data)
        if retained.read_bytes() != data:
            raise ValueError(f'Byte verification failed: {retained}')
        classification, note = DIAGNOSTICS.get(name, (
            'selected_acceptance',
            'Selected green source report; exact case identity deduplication applies.'))
        reports.append(dict(
            name=name, original_path=original.resolve().as_posix(),
            retained_path=retained.relative_to(repo_root).as_posix(), sha256=sha256(data),
            bytes=len(data), **totals, classification=classification,
            selected_for_acceptance=selected, note=note, problems=problems))
        identities_by_report[name] = identities

    origins, chosen = defaultdict(list), {}
    for name in SELECTED:
        for identity in identities_by_report[name]:
            origins[identity].append(name)
            chosen[identity] = name
    overlaps = [dict(classname=identity[0], name=identity[1], reports=names,
                     selected_origin=chosen[identity])
                for identity, names in sorted(origins.items()) if len(names) > 1]
    if len(chosen) != 525:
        raise ValueError(f'Expected 525 unique green selected cases, observed {len(chosen)}')
    selected_cases = [dict(classname=identity[0], name=identity[1], report=origin)
                      for identity, origin in sorted(chosen.items())]
    identity_payload = json.dumps([list(identity) for identity in sorted(chosen)],
                                 ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    for report in reports:
        report['unique_acceptance_cases_attributed'] = sum(origin == report['name'] for origin in chosen.values())
    acceptance = dict(
        identity_key=['classname', 'name'],
        selected_reports_in_precedence_order=SELECTED,
        selected_case_records_before_deduplication=sum(len(identities_by_report[name]) for name in SELECTED),
        unique_green_cases=len(chosen), unique_identity_set_sha256=sha256(identity_payload),
        repeated_case_records_removed=sum(len(names) - 1 for names in origins.values()),
        overlap_case_identities=len(overlaps), overlaps=overlaps, cases=selected_cases,
        note='Case records from repeated runs are not independent tests. Diagnostic runs do not add acceptance coverage.')
    old_manifest = json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else {}
    new_fields = dict(
        schema_version=1, source_collection=dict(
            scope='Completed PR08 source JUnits available at the explicit eighteen-report collection checkpoint.',
            collector='plans/agent_ops/evidence/pr08-observations/collect_reports.py',
            original_temp_root=temp_root.resolve().as_posix(), retained_report_count=len(reports),
            byte_exact_verified=True, reports=reports, acceptance=acceptance))
    if verify_only:
        for key, value in new_fields.items():
            if old_manifest.get(key) != value:
                raise ValueError(f'Manifest verification mismatch for {key}')
    else:
        old_manifest.update(new_fields)
        old_manifest.setdefault('source_collection_created_at', datetime.now(timezone.utc).isoformat())
        manifest_path.write_text(json.dumps(old_manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    return dict(manifest=manifest_path.as_posix(), retained_reports=len(reports),
                unique_green_cases=len(chosen), overlap_case_identities=len(overlaps),
                selected_records=acceptance['selected_case_records_before_deduplication'],
                fixture_failure_errors=next(report['errors'] for report in reports if report['classification'] == 'fixture_failure'),
                verified_only=verify_only)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--temp-root', type=Path, default=Path('C:/Users/jpamb/AppData/Local/Temp'))
    parser.add_argument('--repo-root', type=Path, default=Path(__file__).resolve().parents[4])
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    print(json.dumps(collect(args.temp_root, args.repo_root.resolve(), args.verify_only), indent=2))
