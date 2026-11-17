"""Curate the finished same-home installed service/browser continuity probe."""
import hashlib
import json
from pathlib import Path
import re
import shutil

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
allocation = json.loads((HERE / 'allocation.json').read_text())
root = Path(allocation['root'])
checks = json.loads((root / 'checks-result.json').read_text())
comparison = json.loads((root / 'comparison.json').read_text())
cleanup = json.loads((root / 'physical-cleanup.json').read_text())
stop = json.loads((root / 'stop.json').read_text())
assert checks['status'] == 'PASS' and not comparison['changed'] and comparison['payload_unchanged']
assert cleanup['all_recorded_processes_absent'] and cleanup['listener_absent']
assert stop['state'] == 'stopped' and stop['shutdown_outcome'] == 'drained'
before = json.loads((root / 'before.json').read_text())
after = json.loads((root / 'after.json').read_text())
assert before == after and before['execution_sessions']['count'] == before['execution_operations']['count'] == 0
network = (root / 'requests-cli.log').read_text()
methods = re.findall(r'^\d+\. \[([A-Z]+)\]', network, re.MULTILINE)
assert methods and set(methods) == {'GET'}
sourcepins = json.loads((HERE.parent / 'qc11-package/evidence/source-pins-before.json').read_text())
source_drift = [name for name, pin in sourcepins.items()
                if hashlib.sha256((REPO / name).read_bytes()).hexdigest() != pin]
assert not source_drift, source_drift
payload = json.loads((root / 'payload-after.json').read_text())
assets = {name: pin for name, pin in payload.items() if '/http/static/' in name}
assert any(name.endswith('index-CfDr8rCI.js') for name in assets)
profile, = (Path(allocation['fixture']) / 'quick-cli-home/terminal/profiles').glob('*.json')
assert hashlib.sha256(profile.read_bytes()).hexdigest() == allocation['profile_sha256']
out = HERE / 'evidence'
out.mkdir(exist_ok=True)
for path in root.iterdir():
    if path.is_file() and path.suffix in {'.json', '.log'}:
        shutil.copyfile(path, out / path.name)
for name in ('desktop-home.png', 'connection-context.png'):
    shutil.copyfile(REPO / 'output/playwright/qc25' / name, out / name)
(out / 'source-pins.json').write_text(json.dumps(sourcepins, indent=2) + '\n')
report = dict(status='PASS_F24_D18_REGISTERED_CONNECTION_CONTINUITY_VARIANT',
    source_candidate='fa031697b37a1b879d855f7858f01320addf0df7',
    wheel_sha256='a36e448c80a8190c7e8c92d81ea5a251c4bdf7e370eca0f0b395a5ad29e36cc6',
    fixture_provenance='QC12 git-complete case0, previously connected from Git origin logical-origin and resumed after origin changed to different-name. Original home/DB/root reused, not copied/rekeyed.',
    fixture=allocation['fixture'], home=allocation['home'], root=allocation['project_root'],
    original_server_id=allocation['reference']['server_id'], reference=allocation['reference'],
    logical_name=allocation['logical_name'], connect_id=allocation['connect_id'],
    browser=dict(engine='Playwright CLI real Chrome, automated desktop1440x1100', session='qc25-git-home',
        profile=str(root / 'browser-profile'), profile_personal=False, account_authentication=False,
        readonly_route='Mutating browser methods aborted; no response fulfillment/DTO replacement.',
        dynamic_request_log_count=len(methods), dynamic_methods=sorted(set(methods)),
        screenshots=['evidence/desktop-home.png', 'evidence/connection-context.png']),
    checks=[dict(c, status='PASS', http_status=c['status'])
            if type(c.get('status')) is int and c['status'] == 200 else c for c in checks['checks']],
    service=dict(start=json.loads((root / 'start.json').read_text()), stop=stop, PATH_empty=True,
                 own_environment_homes=True, canonical_lifecycle_only=True, installed_same_home=True,
                 sql_repairs=False, leases_renewed_manually=False),
    persistence=dict(comparison=comparison, before=before, after=after,
        cli_profile_unchanged=True, sessions_before=0, sessions_after=0, operations_before=0, operations_after=0),
    integrity=dict(payload_files=1027, payload_drift=[], source_files=len(sourcepins), source_drift=[], assets=assets),
    cleanup=cleanup,
    antecedent='First wrapper used nonexistent package __main__, exited before lifecycle. Log preserved; only wrapper entrypoint corrected to installed CLI module. One actual lifecycle start succeeded; no start repair/retry.',
    limits=['Registered connection identity/name continuity, not runtime readiness: binding GET reports STALE after retained inert installation disappears under empty PATH.',
        'Board status partial because external source is disabled; other listed sources ready. Unknown totals remain unknown, not zero.',
        'Zero persisted sessions/operations before and after is observed, not multiple-session or I06 qualification.',
        'Inspect execution opens a passive Harness activity dialog. Exact connection target is also resolved by real canonical GET; no execution controls used.',
        'No provider/native invocation, Test/Finish, grant issuance, new identity, Git discovery, credential access, SQL repair, human usability or assistive technology test.',
        'GET request log excludes eight static requests; initialization separately observed static GETs. No full-window console audit claim; initialization/focused checks recorded no errors.',
        'HTTP GET checks in raw result use numeric status200; these are observed HTTP status fields, not a separate failed status classification.',
        'Canonical lifecycle writes its own service/owner metadata; protected binding/grant/receipt/ID/session/operation table snapshots remain exactly unchanged.'])
(HERE / 'qualification.json').write_text(json.dumps(report, indent=2) + '\n')
manifest = {str(p.relative_to(HERE)).replace('\\', '/'):dict(bytes=p.stat().st_size,
    sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in HERE.rglob('*')
    if p.is_file() and p.name != 'manifest.json' and '__pycache__' not in p.parts}
(HERE / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps(dict(qualification_sha256=hashlib.sha256((HERE / 'qualification.json').read_bytes()).hexdigest(),
    manifest_sha256=hashlib.sha256((HERE / 'manifest.json').read_bytes()).hexdigest(), files=len(manifest),
    dynamic_GET_requests=len(methods), source_drift=[])))
