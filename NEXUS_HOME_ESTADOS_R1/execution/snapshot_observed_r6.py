"""Publish a small cross-layer index before the exclusive performance window."""
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
names = [
    'source-tests/r5-working-focal/qualification.json', 'source-tests/r5-home/qualification.json',
    'package-hst-r5/installed-qualification.json', 'package-hst-r6/qualification.json',
    'package-hst-r6/live-qualification.json', 'package-hst-r6/runtime-equivalence-vs-r5.json',
    'installed-supplement-r6/qualification.json', 'frontend-r6-original/qualification.json',
    'browser-hst/r5-r6-final-report.md', 'browser-hst/mobile-intents-derivative.md',
    'scenario-final-review-r5-prepared.json', 'contract-blockers-r6-review.json',
    'results-security-gap-review-r6.json', 'static-checks/r6-supplement.json',
]
report = dict(at=datetime.now(UTC).isoformat(), status='FUNCTIONAL_SCOPES_RECORDED_PERFORMANCE_PENDING',
    runtime_source_commit='90b94ca9673c087554b7dc4a226490ef5417bd32',
    runtime_wheel_sha256='8ab8f08e8f5e06b428ed4642045ad5e4069d93891a869d4dc61fcaa5bb3ffa19',
    counts=dict(source_focal=90, source_home=251, installed_r5=251,
        actual_r6_installed_supplement=11, frontend_node=404),
    report_hashes={name: hashlib.sha256((HERE / name).read_bytes()).hexdigest() for name in names},
    caveats=[
        'Counts are separate cuts, never a combined final-prefix pytest count.',
        'Backend R5 evidence reused only after 1024 exact module payload/dependency-version comparisons.',
        'Browser historical errors, abandoned-transport limitation and invalid coordinate/selector oracles remain visible.',
        'Some unanswered-question cleanup commands reached their guard before normal owner drain. Physical exit0 is not a claim of confirmed runtime.close in every cut.',
        'Only supplied contract/OS/fixture scopes passed. Remaining scenario criteria, native producer limitations, AT, real campaigns and human acceptance are not qualified.',
        'Original broad NOT_GREEN, Quick Connect UNKNOWN usage/QC031 and prior novice-user gates remain.',
    ], human='DEFERRED', paid_provider_calls=0, default_rollout=False,
    performance='Pending original thresholds and paired datasets; no waiver.')
(HERE / 'observed-r6-before-performance.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
print(report['status'])
