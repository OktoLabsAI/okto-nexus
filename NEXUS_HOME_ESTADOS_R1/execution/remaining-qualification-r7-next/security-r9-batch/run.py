"""Gated finite S1/S2 supervisor. This module has not been executed.

Only the installed interpreter launches the application; host imports below
are stdlib, psutil and pinned fixture/control helpers, never checkout product.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time
import shutil

import psutil

HERE = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def write(path, value):
    assert not path.exists(), 'Never overwrite a prior cut'
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


class Commands:
    def __init__(self, root, environment, deadline):
        self.root, self.env, self.deadline = root, environment, deadline
        self.known, self.commands = {}, []
        self.started = time.time()

    def record(self, process):
        try:
            if process.pid not in self.known:
                self.known[process.pid] = dict(pid=process.pid, birth=process.create_time(), exe=process.exe())
        except psutil.NoSuchProcess:
            pass

    def sample(self, pid=None):
        if pid is not None:
            try:
                parent = psutil.Process(pid)
                for process in [parent, *parent.children(recursive=True)]:
                    self.record(process)
            except psutil.NoSuchProcess:
                pass
        # Detached browser/CLI children may outlive their launcher. Discover
        # only processes born in this cut with this exact unique root in argv.
        for process in psutil.process_iter(['pid', 'create_time']):
            try:
                if process.info['create_time'] >= self.started - 1 and any(
                    str(self.root).lower() in part.lower() for part in process.cmdline()
                ):
                    self.record(process)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

    @staticmethod
    def alive(record):
        try:
            process = psutil.Process(record['pid'])
            return abs(process.create_time()-record['birth']) < .01 and process.exe() == record['exe']
        except psutil.NoSuchProcess:
            return False

    def run(self, name, argv, timeout=40, cleanup=False):
        assert name.replace('-', '').isalnum()
        budget = timeout if cleanup else min(timeout, self.deadline-time.monotonic())
        assert budget > 0, 'Owner deadline exceeded before command'
        output = self.root / ('command-' + name + '.private.txt')
        assert not output.exists()
        with output.open('wb') as stream:
            child = subprocess.Popen(argv, cwd=self.root/'cwd', env=self.env,
                stdin=subprocess.PIPE, stdout=stream, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
            child.stdin.close()
            self.sample(child.pid)
            end = time.monotonic()+budget
            while child.poll() is None and time.monotonic() < end:
                self.sample(child.pid)
                time.sleep(.1)
            self.sample(child.pid)
            timed_out = child.poll() is None
        record = dict(name=name, pid=child.pid, exit_code=child.poll(), timed_out=timed_out,
                      raw_sha256=hashlib.sha256(output.read_bytes()).hexdigest())
        self.commands.append(record)
        assert not timed_out, 'Owned command deadline; cleanup only, no retry'
        assert child.returncode == 0, 'Owned command failed; preserve private raw output'
        return output.read_text(encoding='utf-8', errors='replace')

    def remaining(self):
        self.sample()
        return [item for item in self.known.values() if self.alive(item)]

    def contain(self):
        # Root gate explicitly allows this only after normal close/stop.
        remaining = self.remaining()
        for record in reversed(remaining):
            if self.alive(record):
                psutil.Process(record['pid']).terminate()
        end = time.monotonic()+5
        while self.remaining() and time.monotonic() < end:
            time.sleep(.1)
        return {'forced_births':remaining, 'remaining':self.remaining()}


def cli_result(text):
    marker = '### Result\n'
    text = text.replace('\r\n', '\n')
    assert marker in text, 'Missing actual browser result'
    return json.loads(text.split(marker, 1)[1].split('\n###', 1)[0].strip())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--gate', type=Path, required=True)
    args = parser.parse_args()
    preflight = load('security_preflight_run', HERE/'preflight.py')
    before = preflight.check(args.gate)  # Before allocation/process/browser.
    gate = json.loads(args.gate.read_text())
    import re
    assert re.fullmatch(r'hst-security-r9-s1-[a-z0-9-]{1,80}',gate['cut_id'])
    with (HERE/('attempt-'+gate['cut_id']+'.json')).open('x',encoding='utf-8') as attempt:
        attempt.write(json.dumps({'gate_sha256':preflight.sha(args.gate),
                                  'manifest_sha256':preflight.sha(HERE/'prepared-manifest.json')})+'\n')
    browser = preflight.REPO/'NEXUS_HOME_ESTADOS_R1/execution/browser-hst'
    preparation = subprocess.run(['rtk','proxy',sys.executable,'-B',str(HERE/'prepare.py'),
        '--gate',str(args.gate.resolve())], input=b'', capture_output=True, timeout=25, check=True)
    root = Path(json.loads(preparation.stdout)['root']).resolve()
    write(root/'security-guard-before.json', before)
    deadline = time.monotonic()+180
    lifecycle = load('security_containment', browser/'containment.py')
    owner = lifecycle.Owned(root)
    browser_driver = load('security_r9_browser_driver', HERE/'browser_driver.py')
    env = browser_driver.environment(root)
    # Browser path-only host env differs from the separately isolated app env.
    tooling=json.loads((HERE/'prepared-manifest.json').read_text())['browser_tooling']
    explicit_config=root/'playwright-cli.json'
    shutil.copyfile(HERE/'playwright-cli.json',explicit_config)
    commands = Commands(root, env, deadline)
    assert Path(tooling['node']).is_file() and Path(tooling['entry']).is_file()
    rtk = shutil.which('rtk')
    assert rtk, 'Resolve RTK before sanitized child PATH'
    session = gate['cut_id']
    opened, failure, results, diffs, fixture_ready = False, None, [], [], None

    def cli(name, *arguments, cleanup=False):
        return commands.run(name, [rtk,'proxy',tooling['node'],tooling['entry'],'--session='+session,*arguments], cleanup=cleanup)

    def body(name, filename, config):
        target = root/(name+'.js')
        assert not target.exists()
        text = (HERE/filename).read_text(encoding='utf-8')
        assert text.count('__CONFIG__') == 1
        target.write_text(text.replace('__CONFIG__',json.dumps(config)),encoding='utf-8')
        value = cli_result(cli(name,'run-code','--filename='+str(target)))
        write(root/(name+'-result.private.json'), value)
        results.append({'phase':name,'result':value})
        cli(name+'-snapshot','snapshot')
        cli(name+'-screenshot','screenshot','--filename='+str(root/(name+'.png')))
        assert value.get('status','').startswith('PASS_'), 'Browser assertions failed at '+name
        return value

    def control(name):
        marker = root/'control'/name
        assert not marker.exists()
        marker.touch()
        end = min(deadline,time.monotonic()+20)
        while time.monotonic() < end:
            owner.sample()
            commands.sample()
            path = root/'control/controls.json'
            if path.exists() and name in json.loads(path.read_text()).get('done',[]):
                return
            assert owner.process.poll() is None, 'Fixture exited during canonical control'
            time.sleep(.1)
        raise RuntimeError('Canonical control deadline')

    def compare(left, right):
        classifier = load('security_drift', HERE/'drift.py')
        value = classifier.classify(root,left,right,allow_observations=gate['case']=='S2')
        diffs.append(value)
        write(root/('drift-'+left+'-'+right+'.json'),value)
        assert not value['changes'] and not value['expected_observation_errors'], 'Unexpected table drift or missing exact OBS event: preserve FAIL'

    try:
        owner.start(root/'runtime-ready.json',root/'fixture.py')
        end = min(deadline,time.monotonic()+65)
        while not (root/'control/ready.json').exists():
            owner.sample(); commands.sample(owner.process.pid)
            assert owner.process.poll() is None and time.monotonic()<end, 'Fixture not ready before deadline'
            time.sleep(.1)
        fixture_ready = json.loads((root/'control/ready.json').read_text())
        assert fixture_ready['provider_invocations']==0
        origins=json.loads((root/'control/origins.json').read_text())
        prefix=Path(before['python']).resolve().parent.parent
        assert origins['isolated'] is True and Path(origins['prefix']).resolve()==prefix
        assert set(origins['origins'])=={'okto_nexus','nexus_connector_core','okto_nexus_connector'}
        assert all(Path(path).resolve().is_relative_to(prefix) for path in origins['origins'].values())
        url = fixture_ready['url']
        assert url.startswith('http://127.0.0.1:')
        board = json.loads((root/'control/initial-board.json').read_text())
        cards = [item for lane in board['columns'].values() for item in lane['items'] if item['kind']=='harness']
        assert len(cards)==1
        ref = fixture_ready['references'][0]
        cfg = {'url':url,'reference':ref,'baseline_card_ids':[item['id'] for item in cards]}
        cli('open','open','about:blank','--browser=chrome','--profile='+str(root/'browser-profile'),'--config='+str(explicit_config))
        opened=True
        commands.sample()
        argv_proof=browser_driver.capture(root,commands.known,tooling)
        write(root/'browser-argv-before-home.json',argv_proof)
        cli('load-state' ,'state-load',fixture_ready['storage'])
        # Native peer question TTL is unchanged120s; baseline has no question.
        if gate['case']=='S1':
            closed = [item for item in fixture_ready['sessions'] if item['closed']]
            live = [item for item in fixture_ready['sessions'] if not item['closed']]
            assert len(closed)==len(live)==1
            cfg.update(closed_session_id=closed[0]['session_id'],live_session_id=live[0]['session_id'],card_id=cards[0]['id'])
            entries=[item for item in cards[0]['children'] if any(
                linked['session_id']==cfg['live_session_id'] for linked in item['sessions'])]
            assert len(entries)==1, 'Require exact canonical activity, no first/latest fallback'
            cfg['live_entry_id']=entries[0]['id']
            control('security-snapshot-before-get')
            body('passive','s1-passive.js',cfg)
            control('security-snapshot-after-get')
            compare('before-get','after-get')
            body('control-before','s1-revocation.js',dict(cfg,revoked=False))
            control('security-revoke-grant')
            body('control-after','s1-revocation.js',dict(cfg,revoked=True))
        else:
            # First navigation is own Home; this body uses the same explicitly
            # documented local presentation preferences as S1, no backend toggle.
            init = (browser/'initialize-template.js').read_text()
            temporary = root/'initialize.js'
            temporary.write_text(init.replace('__CONFIG__',json.dumps({'url':url,'workspace_id':ref['workspace_id']})))
            cli('initialize','run-code','--filename='+str(temporary))
            control('security-obs-owner')
            cfg['owner']=json.loads((root/'control/security-observation-owner.json').read_text())
            control('security-obs-idle')
            body('idle','s2-reported.js',dict(cfg,completion=False))
            compare('before-obs','after-idle')
            control('security-obs-completion')
            body('completion','s2-reported.js',dict(cfg,completion=True))
            compare('before-obs','after-completion')
    except BaseException as error:
        failure={'type':type(error).__name__,'message':str(error)}
        write(root/'security-failure.private.json',failure)
    finally:
        if opened:
            try: cli('close','close',cleanup=True)
            except BaseException as error:
                failure=failure or {'type':type(error).__name__,'message':'Browser close failed'}
        cleanup = owner.stop(force=gate['allow_own_containment']) if owner.process else {'status':'NOT_STARTED','remaining_known_births':[]}
        commands.sample()
        extra = commands.remaining()
        containment = commands.contain() if extra else {'forced_births':[],'remaining':[]}
        port = int(fixture_ready['url'].rsplit(':',1)[1]) if fixture_ready else None
        listeners = [row.pid for row in psutil.net_connections(kind='tcp') if port and row.status=='LISTEN' and row.laddr.port==port]
        after = None
        helper_guarded = False
        try:
            after=preflight.check(args.gate)
            assert before==after, 'Root gate/source/payload guard changed during cut'
            runtime_config=json.loads((root/'runtime-ready.json').read_text())
            assert preflight.sha(root/'fixture.py')==runtime_config['fixture_sha256']
            assert all(preflight.sha(root/'helpers'/name)==expected
                       for name,expected in runtime_config['helper_pins'].items())
            helper_guarded = True
        except BaseException as error:
            failure=failure or {'type':type(error).__name__,'message':'Final immutable guard failed'}
        final = {'case':gate['case'],'cut_id':gate['cut_id'],'failure':failure,'results':results,'diffs':diffs,
            'before':before,'after':after,'commands':commands.commands,'fixture_cleanup':cleanup,
            'browser_cleanup':containment,'known_births':list(commands.known.values()),'listeners':listeners,
            'provider_invocations':0,'root':str(root),'deadline_seconds':180,
            'runtime_helper_guarded':helper_guarded,
            'browser_environment_policy':'windows-path-allowlist-app-env-own-v1',
            'npx_or_npm_used':False,
            'sampling_limit':'Observed ancestry plus own-root/birth argv scan; not a claim of capturing every short-lived child'}
        final_path=root/'control/final.json'
        fixture_final=json.loads(final_path.read_text()) if final_path.exists() else None
        if fixture_final is None or fixture_final.get('unknown') is not False:
            failure=failure or {'type':'FixtureSettlementUnknown','message':'No complete, known fixture settlement; no retry'}
            final['failure']=failure
        if fixture_final is None or fixture_final.get('unknown') is not False:
            failure=failure or {'type':'FixtureFinalUnknown','message':'No confirmed non-unknown fixture final state'}
            final['failure']=failure
        final['fixture_close_observations']={
            'sessions':fixture_final['sessions'] if fixture_final else None,
            'close_failures':[{'name':path.name,**json.loads(path.read_text())}
                for path in (root/'control').glob('close-failure-*.json')],
            'cleanup_mechanism':'TestClient/embedded-owner lifespan shutdown, then physical process/listener proof',
            'all_runtime_close_receipts_claimed':False,
            'revoked_authority_renewed':False,
            'limit':'Fixture closed=false is retained if runtime.close is refused after revocation; exit0 is not canonical runtime.close PASS',
        }
        write(root/'security-run.private.json',final)
        print(json.dumps({'root':str(root),'case':gate['case'],'failure':failure['type'] if failure else None,
                          'fixture_cleanup':cleanup['status'],'remaining':len(containment['remaining']),
                          'listeners':listeners,'curation_required':True}),flush=True)
    return 1 if failure or cleanup['status']!='EXITED' or cleanup.get('exit_code')!=0 or containment['remaining'] or listeners else 0


if __name__=='__main__':
    raise SystemExit(main())
