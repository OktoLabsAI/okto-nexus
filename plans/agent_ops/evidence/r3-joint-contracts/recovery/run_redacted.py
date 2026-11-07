from pathlib import Path
from datetime import datetime, timezone
import json
import os
import re
import subprocess
import sys
import time

root = Path(__file__).parent
label, *command = sys.argv[1:]
assert re.fullmatch(r'[a-z0-9-]+', label)
assert command[0] == 'rtk'
env = dict(os.environ)
env['PYTHONUTF8'] = '1'
env['PYTHONDONTWRITEBYTECODE'] = '1'
env['PYTEST_ADDOPTS'] = '-o cache_dir=' + (root/'pytest-cache').as_posix()
env['PIP_CACHE_DIR'] = str(root/'pip-cache')
env['UV_CACHE_DIR'] = str(root/'uv-cache')
env['TEMP'] = env['TMP'] = str(root/'runtime-temp')
(root/'runtime-temp').mkdir(exist_ok=True)
def redact(line):
    line = re.sub(r'nxs_[A-Za-z0-9_-]+', '[REDACTED_AGENT_KEY]', line)
    line = re.sub(r'(?i)(Bearer\s+)[^\s\"\'<>]+', r'\1[REDACTED]', line)
    line = re.sub(r'(https?://)[^/\s@]+@', r'\1[REDACTED]@', line)
    line = re.sub(r'\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b','[REDACTED_TOKEN]',line)
    return line
start = datetime.now(timezone.utc).isoformat()
begin = time.monotonic()
with (root/(label+'.log')).open('w',encoding='utf-8') as log:
    process = subprocess.Popen(command,cwd=root,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
        text=True,encoding='utf-8',errors='replace')
    assert process.stdout is not None
    for line in process.stdout:
        log.write(redact(line))
        log.flush()
    code = process.wait()
result = dict(command=command,cwd=str(root),started_at=start,ended_at=datetime.now(timezone.utc).isoformat(),
    elapsed_seconds=time.monotonic()-begin,exit_code=code,log=str(root/(label+'.log')),
    raw_output_stored=False,bytecode_writes_disabled=True)
(root/(label+'.json')).write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
sys.stdout.reconfigure(encoding='utf-8')
print(json.dumps(result,indent=2))
print('\n'.join((root/(label+'.log')).read_text(encoding='utf-8').splitlines()[-35:]))
raise SystemExit(code)
