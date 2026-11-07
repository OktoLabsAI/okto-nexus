from pathlib import Path
import hashlib
import json
import os
import subprocess
import xml.etree.ElementTree as ET
import zipfile

root=Path(__file__).parent
source=root/'nexus-source-v1'
out=root/'nexus-two-mcp-cooperation'
out.mkdir()
python=root/'venv/Scripts/python.exe'
wheel=next((root/'nexus-wheel-v1').glob('*.whl'))
env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','COMSPEC','PATH','PATHEXT','TEMP','TMP'}}
env['SystemRoot']=os.environ['SYSTEMROOT']
for name in ('USERPROFILE','APPDATA','LOCALAPPDATA'):
    env[name]=str(root/'isolated-env'/name.lower())
env.update(PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',OKTO_NEXUS_NO_BANNER='1')
env.update({'NEXUS_AC03_NODE': 'C:/Program Files/nodejs/node.exe', 'NEXUS_AC03_INSPECTOR_ROOT': 'C:/Users/jpamb/AppData/Local/npm-cache/_npx/5a9d879542beca3a/node_modules/@modelcontextprotocol/inspector', 'NEXUS_AC03_PYTHON': 'C:/Python313/python.exe', 'NEXUS_AC03_PYTHON_PATHS': '["C:/Users/jpamb/AppData/Roaming/Python/Python313/site-packages"]'})
client_inputs=[{'path': 'C:\\Users\\jpamb\\AppData\\Local\\npm-cache\\_npx\\5a9d879542beca3a\\node_modules\\@modelcontextprotocol\\inspector\\package.json', 'sha256': 'ac185516b717b4cdb7b1b7dba183661eefb6164ce1c619fa4384171f2d81b81d', 'bytes': 3286}, {'path': 'C:\\Users\\jpamb\\AppData\\Local\\npm-cache\\_npx\\5a9d879542beca3a\\node_modules\\@modelcontextprotocol\\inspector\\cli\\build\\cli.js', 'sha256': '4ebed8a425d72fc8c8855f12165485f6fb1f33fe12e252541858dd4d2db0a4de', 'bytes': 10294}, {'path': 'C:\\Users\\jpamb\\AppData\\Local\\npm-cache\\_npx\\5a9d879542beca3a\\node_modules\\@modelcontextprotocol\\inspector\\cli\\build\\index.js', 'sha256': '3b2873a75c0d7f11044aa5c5a6e8a19523b08eaa21c5295b4188d282ff372512', 'bytes': 10183}, {'path': 'C:\\Users\\jpamb\\AppData\\Local\\npm-cache\\_npx\\5a9d879542beca3a\\node_modules\\@modelcontextprotocol\\inspector\\cli\\build\\client\\index.js', 'sha256': '7f1b1c7be547e854e9e8a3f2b1fc6ad4b43503b174e235e79da87b9b252ae44d', 'bytes': 199}, {'path': 'C:\\Users\\jpamb\\AppData\\Local\\npm-cache\\_npx\\5a9d879542beca3a\\node_modules\\@modelcontextprotocol\\inspector\\cli\\build\\client\\connection.js', 'sha256': '8a6ec5a0a729095f5b6967d1b3c3269449218153cfbbc96b3d868323d84d5ca0', 'bytes': 1171}, {'path': 'C:\\Users\\jpamb\\AppData\\Local\\npm-cache\\_npx\\5a9d879542beca3a\\node_modules\\@modelcontextprotocol\\inspector\\cli\\build\\client\\tools.js', 'sha256': '55274e71b704b25577a833b19b0897106a3a5fa0d4ed119a42b5e703d93d1cd8', 'bytes': 3107}, {'path': 'C:\\Users\\jpamb\\AppData\\Local\\npm-cache\\_npx\\5a9d879542beca3a\\node_modules\\@modelcontextprotocol\\inspector\\cli\\build\\transport.js', 'sha256': 'bbbb454fb3f345b99b98a3c03829a215c1b7800fc994318016fbb2d897b2c5af', 'bytes': 2348}, {'path': 'C:\\Users\\jpamb\\AppData\\Local\\npm-cache\\_npx\\5a9d879542beca3a\\node_modules\\@modelcontextprotocol\\sdk\\package.json', 'sha256': '7ab20eba8fee70f316516b5b3fc45837294caee7e4dd36f2a1593210b0f003ac', 'bytes': 6432}, {'path': 'C:\\Users\\jpamb\\AppData\\Local\\npm-cache\\_npx\\5a9d879542beca3a\\node_modules\\@modelcontextprotocol\\sdk\\dist\\esm\\client\\index.js', 'sha256': 'a5e17addde5d50e0b2a4ac5961d0f59fd044ff47b01b69e715c3b7ab23075bbd', 'bytes': 29673}, {'path': 'C:\\Users\\jpamb\\AppData\\Local\\npm-cache\\_npx\\5a9d879542beca3a\\node_modules\\@modelcontextprotocol\\sdk\\dist\\esm\\client\\streamableHttp.js', 'sha256': '728ae66a1cdeb8bfabc4c0fe2b94ec1e4f7a5575d6c8d269be04229a8f858577', 'bytes': 22393}, {'path': 'C:\\Users\\jpamb\\AppData\\Roaming\\Python\\Python313\\site-packages\\fastmcp\\__init__.py', 'sha256': '680aed4475eb0615774833db82327b4e6e9d23657dc1a2c7dcce31a464d298fc', 'bytes': 827}, {'path': 'C:\\Users\\jpamb\\AppData\\Roaming\\Python\\Python313\\site-packages\\fastmcp\\client\\client.py', 'sha256': 'df306676352c248c771a43c166dcd87b3f976089b456880c14c31c35ccfecf5f', 'bytes': 63206}, {'path': 'C:\\Users\\jpamb\\AppData\\Roaming\\Python\\Python313\\site-packages\\fastmcp\\client\\transports.py', 'sha256': '885a22bee72725bd0ba0356ef476c4816b5adca7314633376ab47879b64e65ca', 'bytes': 43291}, {'path': 'C:\\Users\\jpamb\\AppData\\Roaming\\Python\\Python313\\site-packages\\fastmcp\\client\\auth\\bearer.py', 'sha256': '305105a9c1fabbf57cea6b1888eb0414a37992cd55f419c13623ec3cb1d44eaa', 'bytes': 399}, {'path': 'C:\\Users\\jpamb\\AppData\\Roaming\\Python\\Python313\\site-packages\\mcp\\__init__.py', 'sha256': 'f66ae17959a1420edb67624dcd79da20860543e1d513b7d5c86ec0250cf8af72', 'bytes': 3224}, {'path': 'C:\\Users\\jpamb\\AppData\\Roaming\\Python\\Python313\\site-packages\\mcp\\client\\session.py', 'sha256': '7606a75a9b65cfa21df57901df600a80fdf4bab10ef0bb92abe6aa1cc0db35c9', 'bytes': 25111}, {'path': 'C:\\Users\\jpamb\\AppData\\Roaming\\Python\\Python313\\site-packages\\mcp\\client\\streamable_http.py', 'sha256': 'b4bc6dfdf3b21bace5bb3d19403446ec31c351f786a3217a7686f55dc1bcd6e7', 'bytes': 30450}]
for item in client_inputs:
    assert hashlib.sha256(Path(item['path']).read_bytes()).hexdigest()==item['sha256'], item['path']
selected=['tests/execution_r4/test_two_existing_mcp_clients.py', 'tests/execution_r4/test_two_existing_mcp_cooperation.py']
proof={}
dependencies=json.loads((source/'vendor/ci/manifest.json').read_text())['artifacts']
for w,module in [(wheel,'okto_nexus'),(source/dependencies[0]['path'],'nexus_connector_core'),
                  (source/dependencies[1]['path'],'okto_nexus_connector')]:
    with zipfile.ZipFile(w) as z:
        names=[n for n in z.namelist() if n.startswith(module+'/') and not n.endswith('/')]
        for name in names:
            assert z.read(name)==(root/'venv/Lib/site-packages'/name).read_bytes(),name
            if module=='okto_nexus':assert z.read(name)==(source/'src'/name).read_bytes(),name
        proof[module]={'wheel':str(w),'sha256':hashlib.sha256(w.read_bytes()).hexdigest(),'files':len(names)}
(out/'package-proof.json').write_text(json.dumps(proof,indent=2)+'\n')
(out/'environment.json').write_text(json.dumps({'forwarded_names':sorted(env),'personal_profile_forwarded':False,
    'provider_credentials_forwarded':False,'native_service_registration':False},indent=2)+'\n')
command=[str(python),'-I','-X','utf8',str(source/'tools/ci_installed.py'),'test','--wheel',str(wheel),
    '--output',str(out/'canonical'),'--tests',*selected]
with (out/'tests.txt').open('wb') as log:
    result=subprocess.run(command,cwd=root,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT)
cases=list(ET.parse(out/'canonical/tests.xml').iter('testcase')) if (out/'canonical/tests.xml').exists() else []
summary={'exit':result.returncode,'command':command,'cases':len(cases),
    'failures':[c.attrib for c in cases if c.find('failure') is not None or c.find('error') is not None],
    'skips':[c.attrib for c in cases if c.find('skipped') is not None]}
(out/'result.json').write_text(json.dumps(summary,indent=2)+'\n')
with (out/'pip-check.txt').open('wb') as log:
    check=subprocess.run([str(python),'-m','pip','check'],cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT)

for item in client_inputs:
    assert hashlib.sha256(Path(item['path']).read_bytes()).hexdigest()==item['sha256'], item['path']
(out/'external-client-proof.json').write_text(json.dumps(dict(selected_client_modules=client_inputs,unchanged_before_and_after=True,full_transitive_lock_claim=False),indent=2)+'\n')
print(json.dumps({'exit':result.returncode,'cases':len(cases),'failures':summary['failures'],'pip_check':check.returncode}))
raise SystemExit(result.returncode or check.returncode)
