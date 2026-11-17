"""Window-gated own HTTP supervisor; browser commands remain explicit and separate."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import time

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
READY = HERE.parent / 'package-hst-r7/READY.json'
DATASET = Path('C:/Users/jpamb/AppData/Local/Temp/nexus-hst-performance-open-c7deab6559c14026bbedef93822237d9/dataset.json')


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def driver(public):
    original = (HERE / 'large-dom-driver-prepared.js').read_text(encoding='utf-8')
    needle = 'const cfg = {preparedOnly:true}; // Replace only with future public HTTP READY.'
    assert original.count(needle) == 1
    text = original.replace(needle, 'const cfg = ' + json.dumps(public) + ';')
    text = text.replace('const requests=[],responses=[],errors=[];', 'const requests=[],responses=[],errors=[],assetLoads=[],assets=[];')
    text = text.replace("summary:summary.innerText,project:project.innerText,headers:",
        "summary:summary.innerText,project:project.innerText,projectValue:project.querySelector('select')?.value,headers:")
    text = text.replace("if(u.origin!==origin.origin || u.pathname!=='/api/v1/home/harness-board')return;", """if(u.origin!==origin.origin)return;
    if(u.pathname.startsWith('/assets/'))assetLoads.push((async()=>{
      const body=await r.body(), digest=await crypto.subtle.digest('SHA-256',body);
      assets.push({name:u.pathname.split('/').pop(),status:r.status(),sha256:[...new Uint8Array(digest)].map(b=>b.toString(16).padStart(2,'0')).join('')});
    })());
    if(u.pathname!=='/api/v1/home/harness-board')return;""")
    text = text.replace('while(!responses.length&&Date.now()<deadline)',
        'while(!responses.some(r=>r.version===2)&&Date.now()<deadline)')
    text = text.replace('const response=responses[0];', 'const response=responses.find(r=>r.version===2);')
    text = text.replace("const useful=captured.candidates.find(c=>ordered(c.cards)===ordered(response.cards));", """const countText=(count,label)=>{
    if(!count||count.value===null)return `${label}: unknown`;
    if(count.value===1)label=({'actions':'action','harnesses paused':'harness paused','resume confirmations':'resume confirmation'})[label]??label;
    return `${count.total_is_exact?'':'At least '}${count.value} ${label}`;
  };
  const sourceKeys=['attention','work','results','connections','sessions','correlations','external'];
  if(Object.keys(response.source_status??{}).length!==7||!sourceKeys.every(k=>Object.hasOwn(response.source_status,k)))throw Error('Required coverage fields absent.');
  if(!response.summary)throw Error('Operational summary absent; do not time legacy/shell DOM.');
  const s=response.summary;
  const required=[countText(s.connected,'connected'),countText(s.working,'working'),countText(s.idle,'Idle')];
  for(const key of ['queued','unconfirmed','disconnected'])if(s[key]?.value===null||(s[key]?.value??0)>0)required.push(countText(s[key],key));
  const onlyConfirmation=s.pending_actions.total_is_exact&&s.pending_actions.value===0&&s.blocked_harnesses.total_is_exact&&s.blocked_harnesses.value===0&&(s.resume_confirmations.value??0)>0;
  if(!onlyConfirmation)required.push(countText(s.pending_actions,'actions'),countText(s.blocked_harnesses,'harnesses paused'));
  if(onlyConfirmation||s.resume_confirmations.value===null||(s.resume_confirmations.value??0)>0)required.push(countText(s.resume_confirmations,'resume confirmations'));
  const useful=captured.candidates.find(c=>c.projectValue===cfg.workspace_id&&JSON.stringify(c.headers)===JSON.stringify(['Active','Needs you','Results'])&&ordered(c.cards)===ordered(response.cards)&&required.every(label=>c.summary.includes(label)));
  await Promise.all(assetLoads);
  if(!assets.some(a=>a.name.endsWith('.js'))||!assets.some(a=>a.name.endsWith('.css'))||assets.some(a=>a.status!==200||cfg.assets[a.name]!==a.sha256))throw Error('Served assets do not match installed package.');""")
    text = text.replace("useful,canonicalResponse:response,requests,errors,targetMs:2000", "useful,canonicalResponse:response,requiredSummaryLabels:required,assets,navigationURL:page.url(),requests,errors,targetMs:2000")
    return text


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('action', choices=['server', 'stop'])
    parser.add_argument('--window', required=True, choices=['PERF_DOM_WINDOW_OPEN'])
    parser.add_argument('--root', type=Path)
    args = parser.parse_args()
    if args.action == 'stop':
        root = args.root.resolve()
        assert root.name.startswith('nexus-hst-browser-large-dom-r7-')
        assert json.loads((root / '.owner.json').read_text()) == {'root': str(root), 'kind': 'hst-large-dom-r7-driver'}
        public = json.loads((root / 'http-ready.json').read_text())
        control = Path(public['public_ready_path']).resolve().parent
        fixture_root = control.parent
        assert fixture_root.name.startswith('nexus-hst-performance-large-dom-')
        assert json.loads((fixture_root / '.hst-owned.json').read_text()) == {'root': str(fixture_root), 'kind': 'hst-large-dom-performance-only'}
        (control / 'stop').write_text('Own DOM observation finished\n', encoding='utf-8')
        return
    assert args.root is None, 'New root is allocated only after explicit window'
    ready = json.loads(READY.read_text())
    assert ready['ready'] and ready['prefix_frozen'] and sha(Path(ready['wheel'])) == ready['wheel_sha256']
    assert ready['source_commit'] == '01b0de385398950ac4547aa8a5dcbc29473c12cb'
    root = Path(tempfile.mkdtemp(prefix='nexus-hst-browser-large-dom-r7-')).resolve()
    for name in ('cwd', 'tmp', 'user', 'roaming', 'local'):
        (root / name).mkdir()
    save(root / '.owner.json', {'root': str(root), 'kind': 'hst-large-dom-r7-driver'})
    helper = HERE.parent / 'package-hst-r3/owned_commands.py'
    spec = importlib.util.spec_from_file_location('hst_large_dom_owned', helper)
    owned = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(owned)
    env = {key: value for key, value in os.environ.items() if key.upper() in {'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'SYSTEMDRIVE', 'PATHEXT'}}
    system = Path(env.get('SYSTEMROOT', 'C:/Windows'))
    env.update(PATH=os.pathsep.join((str(system / 'System32'), str(system), str(Path(ready['python']).parent))),
        HOME=str(root / 'user'), USERPROFILE=str(root / 'user'), APPDATA=str(root / 'roaming'), LOCALAPPDATA=str(root / 'local'),
        TMP=str(root / 'tmp'), TEMP=str(root / 'tmp'))
    command = [ready['python'], '-I', '-B', '-X', 'utf8', str(HERE / 'large-dom-http-prepared.py'),
        '--window', args.window, '--ready', str(READY), '--dataset', str(DATASET), '--max-seconds', '240']
    paths = [READY, helper, Path(__file__), HERE / 'large-dom-http-prepared.py', HERE / 'large-dom-driver-prepared.js', HERE / 'benchmark.py', HERE / 'persistent-worker.py']
    pins = {str(path): sha(path) for path in paths}
    print(json.dumps({'phase': 'DISPATCHING', 'root': str(root), 'log': str(root / 'http.log')}), flush=True)
    with (root / 'http.log').open('w', encoding='utf-8') as log, ThreadPoolExecutor(max_workers=1) as pool:
        job = pool.submit(owned.run_owned, command, root=root, cwd=root / 'cwd', env=env, log=log, timeout=270, allow_canonical=False)
        exposed = False
        while not job.done():
            if not exposed:
                for line in (root / 'http.log').read_text(encoding='utf-8', errors='replace').splitlines():
                    if not line.startswith('{'):
                        continue
                    message = json.loads(line)
                    if message.get('ready') and message.get('public_ready'):
                        public = json.loads(Path(message['public_ready']).read_text())
                        public['public_ready_path'] = message['public_ready']
                        public['private_storage_path'] = str(Path(message['public_ready']).parent / 'browser-storage.private.json')
                        save(root / 'http-ready.json', public)
                        (root / 'measurement.js').write_text(driver(public), encoding='utf-8', newline='\n')
                        print(json.dumps({'phase': 'HTTP_READY', 'root': str(root), 'public': str(root / 'http-ready.json'),
                            'script': str(root / 'measurement.js'), 'private_storage_path': public['private_storage_path']}), flush=True)
                        exposed = True
                        break
            time.sleep(.1)
        result = job.result()
    save(root / 'supervisor.json', {'command': command, 'owned_command': result, 'ready_exposed': exposed,
        'pins_before': pins, 'pins_drift': [str(path) for path in paths if sha(path) != pins[str(path)]]})
    print(json.dumps({'phase': 'EXITED', 'root': str(root), 'owned_command': result}), flush=True)
    raise SystemExit(0 if result['success'] and exposed else 1)


if __name__ == '__main__':
    main()
