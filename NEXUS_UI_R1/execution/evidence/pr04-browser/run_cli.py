"""Run prepared code in the already-owned Playwright CLI session, never launch."""
import json
from pathlib import Path
import subprocess

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
out=ROOT/'output/playwright/ui04-final'
ready=json.loads((out/'ready.json').read_text(encoding='utf-8'))
config=dict(ready,expectedBundle=ready['static_build_verified_by_root'],outputDirectory=out.as_posix())
code=(HERE/'probe.js').read_text(encoding='utf-8').replace('__FIXTURE_CONFIG__',json.dumps(config))
# Do not pass hashes/static maps back through a command line unnecessarily.
config={k:config[k] for k in ('url','identities','expectedBundle','outputDirectory')}
code=(HERE/'probe.js').read_text(encoding='utf-8').replace('__FIXTURE_CONFIG__',json.dumps(config))
(out/'prepared-probe.js').write_text(code,encoding='utf-8')
result=subprocess.run(['npx.cmd','--yes','--package','@playwright/cli','playwright-cli','-s=ui04-final','run-code','--filename',str(out/'prepared-probe.js')],
    capture_output=True,text=True,encoding='utf-8',timeout=150,cwd=ROOT)
(out/'output.txt').write_text(result.stdout+'\nSTDERR\n'+result.stderr,encoding='utf-8')
print(result.stdout[-10000:])
print('CLI_EXIT',result.returncode)
