"""Read-only curation of the completed own fixture; no product imports."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
from urllib.parse import urlparse

import psutil

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
allocation = json.loads((HERE / 'allocation.json').read_text())
root = Path(allocation['root'])
out = HERE / 'evidence'
out.mkdir(exist_ok=True)
for name in ['supervisor-result.json', 'owned-processes.json', 'browser-commands.json',
             'checks-result.json', 'helper-pins.json', 'source-before.json',
             'payload-before.json', 'payload-after.json', 'fixture.log']:
    shutil.copyfile(root / name, out / name)
for path in root.glob('*-cli.log'):
    shutil.copyfile(path, out / path.name)
for path in (root / 'control').glob('*.json'):
    shutil.copyfile(path, out / path.name)
for name in ['home.png', 'session-A.png', 'session-B.png']:
    shutil.copyfile(REPO / 'output/playwright/qc31' / name, out / name)
checks = json.loads((out / 'checks-result.json').read_text())
supervisor = json.loads((out / 'supervisor-result.json').read_text())
ready = json.loads((out / 'ready.json').read_text())
final = json.loads((out / 'final.json').read_text())
histories = json.loads((out / 'canonical-histories.json').read_text())
port = urlparse(ready['url']).port
known = json.loads((out / 'owned-processes.json').read_text())
remaining = []
for record in known:
    try:
        process = psutil.Process(record['pid'])
        if abs(process.create_time() - record['created']) < .01:
            remaining.append(record)
    except psutil.NoSuchProcess:
        pass
profile_processes = []
for process in psutil.process_iter(['pid', 'name', 'cmdline']):
    if (process.info['name'] or '').lower() in ['chrome.exe', 'msedge.exe']:
        if str(root / 'browser-profile').lower() in ' '.join(process.info['cmdline'] or []).lower():
            profile_processes.append(process.pid)
listeners = [dict(pid=c.pid, port=port) for c in psutil.net_connections(kind='tcp')
             if c.status == 'LISTEN' and c.laddr.port == port]
cleanup = dict(at=datetime.now(timezone.utc).isoformat(), remaining_owned_births=remaining,
               own_browser_profile_pids=profile_processes, listener= listeners,
               browser_close_exit=next(x['exit_code'] for x in json.loads((out / 'browser-commands.json').read_text()) if x['label']=='close'),
               supervisor_exit=supervisor['exit_code'], peer_exit_codes=final['peers'],
               note='Peer codes are observed as 1, not claimed 0. Canonical close completed; every recorded own birth and the own listener are absent. Data retained.')
(out / 'cleanup.json').write_text(json.dumps(cleanup, indent=2) + '\n')
assert checks['status'] == 'PASS' and all(c['status']=='PASS' for c in checks['checks'])
assert not remaining and not profile_processes and not listeners
assert supervisor['exit_code']==0 and not supervisor['payload_drift'] and not supervisor['source_drift']
assert all(x['method']=='GET' for x in final['browser_requests'])
static = Path(allocation['prefix']) / 'Lib/site-packages/okto_nexus/adapters/inbound/http/static'
assets = {str(p.relative_to(static)): dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
          for p in [static/'index.html', *static.glob('assets/*.js'), *static.glob('assets/*.css')]}
qualification = dict(status='PASS_SCOPED_CANONICAL_MULTISESSIONS', scenario='I06', source_candidate='fa031697b37a1b879d855f7858f01320addf0df7',
    wheel_sha256='a36e448c80a8190c7e8c92d81ea5a251c4bdf7e370eca0f0b395a5ad29e36cc6',
    checks_passed=len(checks['checks']), checks_failed=0, page_errors=checks['errors'],
    provider_invocations=0, fake_protocol=True, browser_requests=len(final['browser_requests']), browser_posts=0,
    reference=ready['reference'], connect_id=ready['connect_id'], sessions=ready['sessions'],
    canonical_histories=[{k:v for k,v in h.items() if k!='events'} for h in histories],
    installed_payload_files=1027, payload_drift=supervisor['payload_drift'], source_drift=supervisor['source_drift'],
    assets=assets, cleanup='evidence/cleanup.json',
    limitations=['Synthetic local Codex protocol peer, no provider or personal account; not paid harness qualification.',
      'A is closed/retained and B is current/READY at browser baseline. Not simultaneous running.',
      'Exact canonical deep links open in fresh own tabs, one mounted viewer at a time. Not a session-picker UX or dirty-navigation test.',
      'Core output and receipts are real canonical ingress from the inert protocol peer; no SQL identities, grants, frames, or journal insertion.',
      'Synthetic source reports missing configuration fields/NATIVE_DISCOVERY_FAILED warning; no native account or model discovery claimed.',
      'History watermark is a pre-browser sample, not a terminal billing fence; projected_through=0 is preserved, not claimed fully projected.',
      'Preserved antecedents include fixture/oracle/control failures and are not promoted to PASS.',
      'No human usability, screen reader, mobile, reconnect or real-provider execution is qualified.'])
(HERE / 'qualification.json').write_text(json.dumps(qualification, indent=2) + '\n')
print(json.dumps(dict(status=qualification['status'], checks=qualification['checks_passed'], requests=qualification['browser_requests'], cleanup=cleanup)))
