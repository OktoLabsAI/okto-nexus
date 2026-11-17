"""Curate a scoped real-browser cut, retaining all negative/oracle evidence."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def read(path):
    raw = path.read_bytes()
    return raw.decode('utf-16' if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig')


def load(path):
    return json.loads(read(path))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cli(name):
    text = read(HERE/name)
    return json.loads(text.split('### Result', 1)[1].split('### Ran Playwright code', 1)[0].strip())


ready, final = load(HERE/'ready.json'), load(HERE/'final.json')
first, continued = cli('checks-cli.txt'), cli('continuation-cli.txt')
mobile, expanded, observed = cli('mobile-cli.txt'), cli('mobile-final-cli.txt'), cli('mobile-observe-cli.txt')
stable = [name for name in final['before'] if final['before'][name] == final['after'][name]]
changed = [name for name in final['before'] if final['before'][name] != final['after'][name]]
assert len(stable) == 8 and changed == ['execution_sessions']
assert all(final['before'][name]['count'] == final['after'][name]['count'] for name in final['before'])
assert not [r for r in final['requests'] if r['method'] not in ('GET', 'HEAD', 'OPTIONS')]
assert observed['status'] == 'PASS'
cleanup = load(HERE/'cleanup-physical.json')
assert cleanup == {'processes': [], 'listeners': []}
before_processes = load(HERE/'own-processes-before.json')
assert all(p['ProcessId'] in (55592, 25104, 43876) for p in before_processes)

screens = HERE/'screens'
screens.mkdir(exist_ok=True)
for source in sorted((ROOT/'output/playwright/qc05').glob('*.png')):
    shutil.copyfile(source, screens/source.name)
current = {name: sha(ROOT/name) for name in ready['source_pins']}
runtime_drift = [name for name in current if current[name] != ready['source_pins'][name]]
assert runtime_drift == ['src/okto_nexus/application/connection_public_ids.py']
functional = [check for check in first['checks'] if check['status'] == 'PASS']
functional += [check for check in continued['checks'] if check['status'] == 'PASS'
               and not check['name'].startswith('GET ')]
functional += [check for check in mobile['checks'] if check['status'] == 'PASS']
functional += [check for check in expanded['checks'] if check['status'] == 'PASS']
functional += observed['checks']
report = dict(version=1, created_at=datetime.now(timezone.utc).isoformat(),
    status='PASS_SCOPED_PUBLIC_ID_UI_WITH_PRESERVED_VIEWER_NEGATIVE', human_acceptance='NOT_RUN',
    ready=dict(url=ready['url'], pid=ready['pid'], home=ready['home'], identities=ready['identities'],
               controlled_clock=ready['controlled_clock']),
    browser=dict(engine='real installed Chrome controlled by Playwright CLI', headed=True,
        session='qc05-public-ids', isolated_profile='playwright_chromiumdev_profile-Um0xs2',
        personal_profile=False, account_auth=False, viewports=['1440x1000', '360x800']),
    commands=dict(
        fixture=['rtk','proxy','C:/Users/jpamb/AppData/Local/Temp/nexus-ui-r3-harness-pr27-gsg_twh1/venv/Scripts/python.exe',
                 '-I','tests/quick_connect/browser_public_ids_fixture.py','--ready',
                 'NEXUS_QUICK_CONNECT_R1/execution/qc05-browser/ready.json','--stop',
                 'NEXUS_QUICK_CONNECT_R1/execution/qc05-browser/stop','--final',
                 'NEXUS_QUICK_CONNECT_R1/execution/qc05-browser/final.json','--expected-bundle',
                 'index-CfDr8rCI.js','--duration','900'],
        browser=['rtk','proxy','npx','--yes','--package','@playwright/cli','playwright-cli',
                 '--session=qc05-public-ids','open',ready['url'],'--headed'],
        check_command_prefix=['rtk','proxy','npx','--yes','--package','@playwright/cli','playwright-cli',
                              '--session=qc05-public-ids','run-code','--filename'],
        scripts=['NEXUS_QUICK_CONNECT_R1/execution/qc05-browser/checks-run.js',
                 'NEXUS_QUICK_CONNECT_R1/execution/qc05-browser/continuation-run.js',
                 'tests/quick_connect/browser_public_ids_mobile.js',
                 'tests/quick_connect/browser_public_ids_mobile_final.js',
                 'tests/quick_connect/browser_public_ids_mobile_observe.js'],
        cleanup='playwright-cli --session=qc05-public-ids close; then own fixture stop-file; observed process exit0'),
    functional_checks=functional,
    raw_cuts=[dict(file=file, status=value['status'], message=value.get('message'))
              for file, value in [('checks-cli.txt',first),('continuation-cli.txt',continued),
                                  ('mobile-cli.txt',mobile),('mobile-final-cli.txt',expanded),
                                  ('mobile-observe-cli.txt',observed)]],
    session_drift_diagnostic=load(HERE/'session-diagnostic.json'),
    http_path_counts={path:sum(r['path']==path for r in final['requests']) for path in sorted({r['path'] for r in final['requests']})},
    interpretation=[
        'Initial selector/catalog checks passed. First driver expected home-detail/URL after Open connection; real UI correctly opens the distinct Connection context dialog. The timeout is preserved as an oracle error; no Open click was repeated.',
        'Continuation proves exact saved context plus canonical seven-field binding, four basic destinations, same IDs/context across Active/Needs you/Results, legacy fallback and explicit delivery target.',
        'Historical ui-success has synthetic projection receipts with canonical_frame NULL and ui-session-2 has no retained watermark. Viewer correctly returns DB_ERROR503 and stream404; this is preserved as a negative fixture and not accepted as a successful viewer.',
        'First mobile driver looked for Open navigation rather than the existing Expand navigation label. Explicit fresh-snapshot toggle showed four destinations. Backdrop center is occluded by the sidebar at360; Escape closed navigation and returned visible focus. Both driver failures remain raw; no product change was made.',
    ],
    negative_viewer=dict(status='NOT_VERIFIED_POSITIVE_VIEWER', target=dict(kind='result',
        operation_id='ui-success',session_id='ui-session-2',workspace_id='ws'),
        receipt_error=dict(status=503,code='DB_ERROR',message='Stored operation receipt history is invalid.'),
        stream_error=dict(status=404,reason='synthetic historical session has no retained stream watermark'),
        no_forged_frame=True, no_product_relaxation=True),
    passive_effects=dict(requests=len(final['requests']), mutations=0,
        stable_protected_tables=stable, changed_tables=changed,
        counts_unchanged=True, grants_operations_bindings_agents_receipts_public_ids_byte_equal=True,
        session_digest_change='Observed but not attributed: baseline stores a digest, not old session rows. No claim of zero total Server writes or no canonical background maintenance.',
        requests_file='requests.json'),
    runtime_source_pins=ready['source_pins'], current_source_pins=current,
    source_drift=runtime_drift,
    drift_explanation='Root explicitly added bounded cursor RecursionError handling while this fixture was live. Loaded source cut is preserved separately; static assets did not drift. Browser does not exercise adversarial cursor parser.',
    cleanup=dict(mode='normal Playwright close plus own fixture stop-file', force_used=False,
        fixture_exit_code=0, owned_wss_lifespan_factory_closed=True, own_port=63926,
        own_listener_absent=True, own_processes_absent=True, before_file='own-processes-before.json',
        after_file='cleanup-physical.json', listener_after='cleanup-physical.json'),
    boundaries=dict(real_provider_calls=0, provider_auth_reads=0, native_harness_cli_calls=0,
        setup_tests_during_browsing=0, finish_during_browsing=0, grant_changes_during_browsing=0,
        public_associations_before_baseline=2, synthetic_registered_bindings=3,
        underlying_fixture='Existing admitted inert WSS question; explicit extra registered/historical SQL read facts.',
        current_installed_package=False, personal_install=False, git_mutations=False, ledger_edits=False),
    screenshots={str(p.relative_to(HERE)).replace('\\','/'):sha(p) for p in screens.glob('*.png')},
)
(HERE/'requests.json').write_text(json.dumps(final['requests'],indent=2)+'\n',encoding='utf-8')
(HERE/'qualification.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
sources = list((ROOT/'tests/quick_connect').glob('browser_public_ids*'))
manifest = {str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for p in sources if p.is_file()}
manifest.update({str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for p in HERE.rglob('*')
                 if p.is_file() and '__pycache__' not in p.parts and p.name != 'manifest.json'})
(HERE/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(report=str(HERE/'qualification.json'),sha256=sha(HERE/'qualification.json'),
                     checks=len(functional),requests=len(final['requests']),stable_tables=len(stable),screenshots=len(report['screenshots']))))
