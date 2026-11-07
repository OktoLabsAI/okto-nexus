"""Only local import/help probes; no Server, socket, credentials or model."""
import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).parent
TEST = Path('D:/Projetos/Techridy/okto_labs_okto_nexus/tests/execution_r4/test_two_existing_mcp_clients.py')
INSPECTOR = Path('C:/Users/jpamb/AppData/Local/npm-cache/_npx/5a9d879542beca3a/node_modules/@modelcontextprotocol/inspector')
PACKAGES = Path('C:/Users/jpamb/AppData/Roaming/Python/Python313/site-packages')
NODE = 'C:/Program Files/nodejs/node.exe'
PYTHON = 'C:/Python313/python.exe'
strings = {node.targets[0].id: ast.literal_eval(node.value) for node in ast.parse(TEST.read_text(encoding='utf-8')).body
           if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)}
env = {k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','COMSPEC'}}
home = ROOT/'synthetic-home'
home.mkdir(exist_ok=True)
env.update(PATH='C:/Windows/System32', HOME=str(home), USERPROFILE=str(home), APPDATA=str(home),
    LOCALAPPDATA=str(home), TEMP=str(home), TMP=str(home), FASTMCP_LOG_ENABLED='false',
    PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8')
results = []
def run(name, argv, data=None):
    value = subprocess.run(argv, input=None if data is None else json.dumps(data)+'\n',
        cwd=ROOT, env=env, text=True, encoding='utf-8', capture_output=True, timeout=45,
        creationflags=subprocess.CREATE_NO_WINDOW)
    (ROOT/(name+'.stdout.txt')).write_text(value.stdout,encoding='utf-8')
    (ROOT/(name+'.stderr.txt')).write_text(value.stderr,encoding='utf-8')
    results.append(dict(name=name,argv=argv,returncode=value.returncode,stdout=value.stdout,stderr=value.stderr))
    return value
for key, name in [('INSPECTOR_DRIVER','inspector.mjs'),('FASTMCP_DRIVER','fastmcp.py')]:
    (ROOT/name).write_text(strings[key],encoding='utf-8')
run('node-version',[NODE,'--version'])
run('python-version',[PYTHON,'-I','--version'])
run('inspector-help',[NODE,str(INSPECTOR/'cli/build/index.js'),'--help'])
run('inspector-import',[NODE,str(ROOT/'inspector.mjs')],dict(probe=True,inspector=str(INSPECTOR)))
run('fastmcp-import',[PYTHON,'-I',str(ROOT/'fastmcp.py')],dict(probe=True,dependency_paths=[str(PACKAGES)]))
files = [INSPECTOR/p for p in ['package.json','cli/build/cli.js','cli/build/index.js','cli/build/client/index.js',
    'cli/build/client/connection.js','cli/build/client/tools.js','cli/build/transport.js']]
files += [INSPECTOR.parent/'sdk'/p for p in ['package.json','dist/esm/client/index.js','dist/esm/client/streamableHttp.js']]
files += [PACKAGES/'fastmcp'/p for p in ['__init__.py','client/client.py','client/transports.py','client/auth/bearer.py']]
files += [PACKAGES/'mcp'/p for p in ['__init__.py','client/session.py','client/streamable_http.py']]
inputs = [dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size) for p in files]
(ROOT/'local-capabilities.json').write_text(json.dumps(dict(probes=results,inputs=inputs,
    clients_exercised_over_network=False,provider_calls=0,personal_credentials_read=False,
    source= str(TEST),source_sha256=hashlib.sha256(TEST.read_bytes()).hexdigest()),indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(probes=[dict(name=x['name'],returncode=x['returncode']) for x in results],input_count=len(inputs))))
