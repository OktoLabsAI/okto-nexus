"""Static S1/R9 derivation; no application/browser/allocation."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import shutil

HERE=Path(__file__).resolve().parent
OLD=HERE.parent/'security-batch'
assert hashlib.sha256((OLD/'prepared-manifest.json').read_bytes()).hexdigest()=='37f0fea6bd0b0363d0fb9292d9b277a6041355d8c1a182964288169bc5b7bf01'


def replace(text, before, after):
    assert text.count(before)==1,before
    return text.replace(before,after,1)


for name in ('fixture_builder.py','security_controls.py','drift.py','assert_captures.py',
             's1-passive.js','s1-revocation.js'):
    assert not (HERE/name).exists()
    shutil.copyfile(OLD/name,HERE/name)
text=(OLD/'preflight.py').read_text()
text=text.replace('6eaa325ea3ddf1dec1b03475b27f373211c81e53','f07163ab7fd618b2ff4247ba6cdb2547b5d4e038')
text=text.replace('fc2afcccdf55236db21071a132a353a13cf1c56399767ea5223a69e50162902e','e870ea400435d5b736093990af9b56544661e205ad657bbff83f830421a3e628')
text=text.replace('package-hst-r8','package-hst-r9')
text=replace(text,"assert gate['case'] in {'S1', 'S2'} and gate['deadline_seconds'] == 180",
    "assert gate['case'] == 'S1' and gate['deadline_seconds'] == 180")
text=replace(text,"    assert gate['allow_own_containment'] is True",'''    assert gate['allow_own_containment'] is True
    assert gate['browser_environment_policy']=='windows-path-allowlist-app-env-own-v1'
    browser=manifest['browser_tooling']
    assert sha(browser['node'])==browser['node_sha256'] and sha(browser['chrome'])==browser['chrome_sha256']
    tool=Path(browser['node_modules']).resolve()
    actual={path.relative_to(tool).as_posix():sha(path)
        for package in ('@playwright/cli','playwright','playwright-core')
        for path in (tool/package).rglob('*') if path.is_file()}
    assert actual==browser['cli_payload_pins']
    assert Path(browser['entry']).resolve().is_relative_to(tool)
    assert json.loads((HERE/'playwright-cli.json').read_text())==browser['browser_config']''')
(HERE/'preflight.py').write_text(text)
text=(OLD/'prepare.py').read_text().replace('package-hst-r8','package-hst-r9')
(HERE/'prepare.py').write_text(text)
original=(OLD/'run.py').read_text()
text=replace(original,'import os\n','')
text=replace(text,'    env = lifecycle.environment(root)',
    "    browser_driver = load('security_r9_browser_driver', HERE/'browser_driver.py')\n    env = browser_driver.environment(root)")
text=replace(text,"    env['PATH'] = str(Path(r'C:/Program Files/nodejs')) + os.pathsep + str(Path(os.environ['SYSTEMROOT'])/'System32')\n    env['npm_config_cache'] = str(root/'npm-cache')\n    env['npm_config_userconfig'] = str(root/'no-user-npmrc')",'''    # Browser path-only host env differs from the separately isolated app env.
    tooling=json.loads((HERE/'prepared-manifest.json').read_text())['browser_tooling']
    explicit_config=root/'playwright-cli.json'
    shutil.copyfile(HERE/'playwright-cli.json',explicit_config)''')
text=replace(text,"    npx = Path(r'C:/Program Files/nodejs/npx.cmd')\n    assert npx.is_file()", "    assert Path(tooling['node']).is_file() and Path(tooling['entry']).is_file()")
text=replace(text,"[rtk,'proxy',str(npx),'--yes','--package','@playwright/cli',\n            'playwright-cli','--session='+session,*arguments]",
    "[rtk,'proxy',tooling['node'],tooling['entry'],'--session='+session,*arguments]")
text=replace(text,"cli('open','open','about:blank','--browser=chrome','--profile='+str(root/'browser-profile'))",
    "cli('open','open','about:blank','--browser=chrome','--profile='+str(root/'browser-profile'),'--config='+str(explicit_config))")
text=replace(text,"        opened=True\n        cli('load-state'",'''        opened=True
        commands.sample()
        argv_proof=browser_driver.capture(root,commands.known,tooling)
        write(root/'browser-argv-before-home.json',argv_proof)
        cli('load-state' ''')
# Keep argument whitespace syntactically harmless and all existing assertions.
text=replace(text,"            'runtime_helper_guarded':helper_guarded,", "            'runtime_helper_guarded':helper_guarded,\n            'browser_environment_policy':'windows-path-allowlist-app-env-own-v1',\n            'npx_or_npm_used':False,")
text=replace(text,"    gate = json.loads(args.gate.read_text())",'''    gate = json.loads(args.gate.read_text())
    import re
    assert re.fullmatch(r'hst-security-r9-s1-[a-z0-9-]{1,80}',gate['cut_id'])
    with (HERE/('attempt-'+gate['cut_id']+'.json')).open('x',encoding='utf-8') as attempt:
        attempt.write(json.dumps({'gate_sha256':preflight.sha(args.gate),
                                  'manifest_sha256':preflight.sha(HERE/'prepared-manifest.json')})+'\\n')''')
ast.parse(text)
(HERE/'run.py').write_text(text)
(HERE/'run-r8-r9.diff').write_text(''.join(difflib.unified_diff(original.splitlines(True),text.splitlines(True),
    fromfile='R8/security-batch/run.py',tofile='R9/security-r9-batch/run.py')))
text=(OLD/'curate.py').read_text()
text=replace(text,"    origin_path=root/'control/origins.json'",'''    argv_path=root/'browser-argv-before-home.json'
    report['browser_environment_policy']='windows-path-allowlist-app-env-own-v1'
    report['npx_or_npm_used']=False
    if argv_path.exists():report['actual_own_browser_before_home']=json.loads(argv_path.read_text())
    origin_path=root/'control/origins.json' ''')
ast.parse(text)
(HERE/'curate.py').write_text(text)
config=OLD/'explicit-chrome/browser-only-v2/playwright-cli.json'
shutil.copyfile(config,HERE/'playwright-cli.json')
for path in HERE.glob('*.py'):
    ast.parse(path.read_text())
print(json.dumps({'status':'STATIC_S1_R9_PREPARED','runtime_started':False,'browser_started':False}))
