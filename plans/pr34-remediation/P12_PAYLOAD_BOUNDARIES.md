# Native option and payload authority boundaries

2026-09-24; feature/v0.2.0; parent04446f738675e768245a371fb39fb027949d041e plus changed source/test hashes.

A real composition regression exposed a REST/MCP contract mismatch. The application validator rejected forbidden control fields, but REST send/steer/interrupt normalized the payload outside their OktoNexusError handler. Each returned INTERNAL/HTTP500 while MCP returned VALIDATION_ERROR. No unauthorized effect was admitted, but the client-facing error contract was wrong.

The production change moves only these three normalization calls inside the existing error mapping. Authorization still precedes validation; no approved options, permissions, launch behavior, schema or sandbox controls change.

New test_runtime_payload_boundaries.py checks five unapproved launch options (cwd, sandbox, provider, env, argv) over REST/MCP with zero spawns. It then checks actor_agent_id, from_agent_id, grant_id, root_operation_id and those same native options on send, steer and interrupt, with zero command rows and zero native writes. Every field is tested through both actual surfaces.

Initial Windows19763:1 PASS1 FAIL8.82s, genuine REST500 versus expected422. Expanded reproduction62695:1 PASS3 FAIL13.36s, all three controls reproduce. Persistent RED XML and pre-fix source/test hashes are retained; sanitized node results omit captured tracebacks. Production changes started only after this RED run completed.

```text
rtk proxy .venv/Scripts/python.exe -m pytest -q --tb=line --junitxml=.git/pr34-evidence/payload-04446f7-red-windows.xml tests/test_runtime_payload_boundaries.py
rtk proxy .venv/Scripts/python.exe -m pytest -q --tb=short --junitxml=.git/pr34-evidence/payload-04446f7-windows.xml tests/test_runtime_payload_boundaries.py tests/test_runtime_grants.py tests/test_runtime_work_results.py tests/test_runtime_operation_authorization.py
rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q --tb=short --junitxml=.git/pr34-evidence/payload-04446f7-linux.xml tests/test_runtime_payload_boundaries.py tests/test_runtime_grants.py tests/test_runtime_work_results.py tests/test_runtime_operation_authorization.py
rtk proxy ruff check src/okto_nexus/adapters/inbound/http/routes.py tests/test_runtime_payload_boundaries.py
```

Ruff PASS. Required live stdio MCP smoke also PASS, exit0, LIVE E2E RESULT: PASS. The launcher below retained only OS launch variables, set temporary homes and source PYTHONPATH, and disabled harness integration for this baseline smoke. Feature-enabled tests above remain the acceptance gate. Log C:/Users/jpamb/AppData/Local/Temp/okto-pr34-live-smoke-gv0ab5k7/result.log. No native provider campaign repeated.

```powershell
rtk proxy .venv/Scripts/python.exe -X utf8 -c @'
import os,subprocess,sys,tempfile
from pathlib import Path
base=Path(tempfile.mkdtemp(prefix='okto-pr34-live-smoke-'))
env={k:v for k,v in os.environ.items() if k.upper() in {'PATH','SYSTEMROOT','WINDIR','TEMP','TMP'}}
env.update(HOME=str(base),USERPROFILE=str(base),PYTHONPATH=str(Path('src').resolve()),PYTHONIOENCODING='utf-8',OKTO_NEXUS_FEATURE_HARNESS_INTEGRATIONS='false')
with (base/'result.log').open('w',encoding='utf-8') as log:
 result=subprocess.run([sys.executable,'scripts/live_client.py'],env=env,stdout=log,stderr=subprocess.STDOUT)
output=(base/'result.log').read_text(encoding='utf-8')
print('log='+str(base/'result.log'));print('exit_code='+str(result.returncode));print('\n'.join(line for line in output.splitlines() if 'LIVE E2E RESULT:' in line))
if result.returncode: print(output[-2500:])
raise SystemExit(result.returncode)
'@
```

T-AUTH-10 maps to the complete new option rejection cases. Payload identity checks and existing forged structured-result tests add T-AUTH-07 coverage, but the original native grant/root field stimuli remain unqualified; that requirement is not promoted merely from payload tests. Final release, full matrix, leak/load and comparative performance gates remain open.

Expanded Windows96750:37 PASS130.90s/Linux40250:37 PASS150.04s, both exit0. Persistent XMLs reduced; all mapped parameters verified PASS on both. Source/tests frozen during execution. Parent plus source/test hashes in p12-payload-boundaries.json. T-AUTH-10 scoped PASS. No live test processes remain.
