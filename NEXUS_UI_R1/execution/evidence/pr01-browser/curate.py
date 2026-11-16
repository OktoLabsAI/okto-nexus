"""Curate only this agent's finite shell-browser evidence; no runtime actions."""
from pathlib import Path
import hashlib
import json
import shutil

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
CONTROLS = {
    'antecedent': Path((HERE/'control.txt').read_text().strip()),
    'main': Path((HERE/'control-final.txt').read_text().strip()),
    'flags': Path((HERE/'control-flags.txt').read_text().strip()),
}


def result(name):
    path = HERE/name
    data = path.read_bytes()
    text = data.decode('utf-16') if data.startswith(b'\xff\xfe') else data.decode('utf-8-sig')
    text = text.replace('\r\n', '\n')
    value = json.loads(text.split('### Result\n', 1)[1].split('\n### Ran', 1)[0])
    path.write_text(text, encoding='utf-8')
    return value


main = result('output-final.txt')
flags = result('flags-output.txt')
(HERE/'results.json').write_text(json.dumps({'main': main, 'flags': flags}, indent=2)+'\n', encoding='utf-8')
for key, control in CONTROLS.items():
    shutil.copyfile(control/'ready.json', HERE/f'{key}-ready.json')
for name in ['desktop-home', 'desktop-advanced', 'canonical-approval', 'mobile-advanced', 'memory-on', 'attention-off-approvals']:
    shutil.copyfile(ROOT/f'output/playwright/ui-r1-shell/{name}.png', HERE/f'{name}.png')

sources = ['frontend/src/App.tsx', 'frontend/src/navigationRegistry.ts', 'frontend/src/components/NavigationSidebar.tsx',
    'frontend/src/components/GlobalAttentionButton.tsx', 'frontend/src/views/AdvancedView.tsx',
    'frontend/src/attentionSummaryState.ts', 'frontend/src/hooks/useScopedAttentionSummary.ts',
    'frontend/src/hooks/useObservationRead.ts', 'frontend/src/observationReader.ts',
    'frontend/src/views/HomeView.tsx', 'frontend/src/views/MetaHarnessView.tsx',
    'frontend/src/components/HelpModal.tsx', 'frontend/src/components/onboarding/OnboardingModal.tsx',
    'frontend/src/operatorUnread.ts', 'tests/home_evolution/browser_fixture.py',
    'src/okto_nexus/adapters/inbound/http/app.py', 'src/okto_nexus/adapters/inbound/http/routes.py',
    'src/okto_nexus/adapters/inbound/http/static/index.html',
    'src/okto_nexus/adapters/inbound/http/static/assets/index-6o2k3pzt.js',
    'src/okto_nexus/adapters/inbound/http/static/assets/index-CqPDZl5S.css']
pins = {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in sources}
for name in ['probe.js', 'flags-probe.js', 'fixture.py']:
    pins[name] = hashlib.sha256((HERE/name).read_bytes()).hexdigest()
(HERE/'source-pins.json').write_text(json.dumps(pins, indent=2)+'\n', encoding='utf-8')

qualification = {
    'status': 'SCOPED_BROWSER_CHECKS_PASS_WITH_EXPLICIT_UNTESTED_BOUNDARIES',
    'product_version': '0.3.5', 'baseline_bump_head': '9de55d95',
    'head_at_curation': '736f36b2d3e493b274c729811ef54401c444c99c',
    'runtime_source': 'Frozen frontend working tree; source-pins.json is authoritative for tested bytes, not an assumption that frontend was already committed.',
    'bundle': 'index-6o2k3pzt.js', 'css': 'index-CqPDZl5S.css',
    'main_checks_pass': len(main['checks']), 'flag_checks_pass': 6,
    'actual_http_denials': [{'status':401, 'code':'AUTH_FAILED', 'scope':'Invalid fixture credential on canonical /api/v1/approvals'},
                           {'status':403, 'code':'CROSS_ORIGIN_BLOCKED', 'scope':'Cross-origin loopback trust boundary; not delegated-agent ACL'}],
    'browser_page_errors': main['errors']+flags['errors'], 'browser_console_errors':main['consoleErrors']+flags['consoleErrors'],
    'mutation_requests': [r for data in (main,flags) for r in data['requests'] if r['method'] not in {'GET','HEAD','OPTIONS'}],
    'covered': ['Five navigation destinations, legacy data-view IDs and four purpose groups',
                'Policies advanced selection and Advanced/group/page breadcrumb; no all-pages browser claim',
                'Memory OFF visibility and ON visibility from real info response',
                'Classic Home scoped3 versus global4 summary; two canonical pending approvals in global queue',
                'Graph entry, independent resolved queue filter and project switch, passive exact approval inspector',
                'Conversations operator seen marker; Home does not advance it; no HTTP seen mutation exists in this path',
                '360 CSSpx keyboard navigation across five destinations, collapsed menu, visible focus observations and actual menu-control hit-tests; document width360',
                'Attention OFF globally reachable fallback and real canonical approvals page',
                'Actual401 and cross-origin403 on canonical advanced read API'],
    'not_claimed': ['New unified Home projection, standalone session target or two-harness onboarding',
                    'Full T-NAV-03 every destination exercised in browser',
                    'Delegated-agent403 or authorization to mutate; no mutation attempted',
                    'Native question generated while Graph/Artifacts open; seeded pending approvals were used',
                    'Native200percent zoom, actual screen-reader speech or human comprehension',
                    'Dirty-form navigation guard or synthetic401/403 UI interception',
                    'Unsupported bookmark-by-view route, automatic focus transfer after menu animation, all native hosts or personal authentication'],
    'cleanup': [
        {'variant':'antecedent','browser_pid':10208,'browser_close_exit_code':0,'pid_absent':True,'fixture_exec_session':97425,'fixture_exit_code':0,'port':64078},
        {'variant':'main','browser_pid':42252,'browser_close_exit_code':0,'pid_absent':True,'fixture_exec_session':75632,'fixture_exit_code':0,'port':50224},
        {'variant':'flags','browser_pid':51756,'browser_close_exit_code':0,'pid_absent':True,'fixture_exec_session':40011,'fixture_exit_code':0,'port':64945}],
    'all_three_ports_listening_after_cleanup':0,
    'antecedents': 'Retained selector timeout, valid transient stale badge and initial info timing/case-sensitive test assertion mistakes. Final checks wait for actual controls/data and respect explicit stale counts; no product modifications made.',
    'raw_flags_status_note': 'The HTTP401 check data uses status:401, which overrides its PASS string in the raw helper spread. Actual denied.status()===401 was asserted and the overall runner passed; qualification records the HTTP result explicitly.'}
(HERE/'qualification.json').write_text(json.dumps(qualification, indent=2)+'\n', encoding='utf-8')
for name in ['control.txt','control-final.txt','control-flags.txt']:
    (HERE/name).unlink()
print('qualification SHA256', hashlib.sha256((HERE/'qualification.json').read_bytes()).hexdigest())
