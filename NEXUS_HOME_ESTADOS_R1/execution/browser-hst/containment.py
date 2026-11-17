"""Own fixture lifecycle; importing does not start anything."""
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time

import psutil


def environment(root):
    root=Path(root).resolve();assert root.name.startswith('nexus-hst-')
    env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','COMSPEC','PATHEXT','SYSTEMDRIVE','OS','PROCESSOR_ARCHITECTURE'}}
    for key,name in [('HOME','os-home'),('USERPROFILE','os-home'),('APPDATA','appdata'),('LOCALAPPDATA','localappdata'),
                     ('TEMP','tmp'),('TMP','tmp'),('CODEX_HOME','codex-home'),('CLAUDE_CONFIG_DIR','claude-home')]:
        path=root/name;path.mkdir(exist_ok=True);env[key]=str(path)
    env.update(PATH='',GIT_CONFIG_GLOBAL=os.devnull,GIT_CONFIG_SYSTEM=os.devnull,GIT_CONFIG_NOSYSTEM='1',
        PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1')
    return env


def require_ready(path):
    value=json.loads(Path(path).read_text())
    assert value.get('approved_to_start') is True,'No Root start authorization / installed READY'
    assert value.get('provider_invocations')==0
    python=Path(value['python']).resolve();assert python.is_absolute() and python.exists()
    prefix=python.parent.parent
    wheel=Path(value['wheel']).resolve()
    assert hashlib.sha256(wheel.read_bytes()).hexdigest()==value['wheel_sha256']
    for kind in ['js','css']:
        asset=Path(value[kind+'_asset']).resolve()
        assert asset.is_relative_to(prefix) and hashlib.sha256(asset.read_bytes()).hexdigest()==value[kind+'_sha256']
    assert '0.3.7' in wheel.name
    return value


class Owned:
    def __init__(self,root):
        self.root=Path(root).resolve();assert self.root.name.startswith('nexus-hst-')
        self.process=None;self.known={};self.signals=[];self.log=None

    def sample(self):
        try:
            process=psutil.Process(self.process.pid)
            for item in [process,*process.children(recursive=True)]:
                if item.pid not in self.known:
                    self.known[item.pid]=dict(pid=item.pid,birth=item.create_time(),exe=item.exe(),
                        argv_sha256=hashlib.sha256(' '.join(item.cmdline()).encode()).hexdigest())
        except psutil.NoSuchProcess:pass

    def alive(self,record):
        try:
            item=psutil.Process(record['pid'])
            return abs(item.create_time()-record['birth'])<.01 and item.exe()==record['exe']
        except psutil.NoSuchProcess:return False

    def start(self,ready,script):
        config=require_ready(ready)
        assert self.process is None
        script=Path(script).resolve()
        assert script.is_relative_to(self.root)
        assert hashlib.sha256(script.read_bytes()).hexdigest()==config['fixture_sha256']
        for name,expected in config['helper_pins'].items():
            helper=(self.root/'helpers'/name).resolve()
            assert helper.is_relative_to(self.root/'helpers')
            assert hashlib.sha256(helper.read_bytes()).hexdigest()==expected
        cwd=self.root/'cwd';cwd.mkdir(exist_ok=True)
        self.log=(self.root/'fixture.log').open('w',encoding='utf-8')
        self.process=subprocess.Popen([config['python'],'-I','-B',str(script)],cwd=cwd,env=environment(self.root),
            stdin=subprocess.PIPE,stdout=self.log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        self.process.stdin.close();self.sample()
        return self.process.pid

    def stop(self,*,force=False):
        assert self.process is not None
        control=self.root/'control';control.mkdir(exist_ok=True);(control/'stop').touch()
        def wait(seconds):
            end=time.monotonic()+seconds
            while self.process.poll() is None and time.monotonic()<end:
                self.sample();time.sleep(.25)
        wait(15)
        if self.process.poll() is None and force:
            # Dedicated group only. Never prefix-kill or kill by process name.
            self.process.send_signal(signal.CTRL_BREAK_EVENT);self.signals.append('own group CTRL_BREAK');wait(8)
            if self.process.poll() is None:
                self.sample()
                for record in reversed(list(self.known.values())):
                    if self.alive(record):psutil.Process(record['pid']).terminate()
                self.signals.append('exact own birth/exe termination');wait(5)
        code=self.process.poll()
        remaining=[r for r in self.known.values() if self.alive(r)]
        if code is not None:self.log.close()
        result=dict(exit_code=code,remaining_known_births=remaining,signals=self.signals,
            status='EXITED' if code is not None and not remaining else 'INCOMPLETE_PRESERVED',
            sampling_limit='0.25s cannot inventory every short-lived child',data_preserved=True)
        (control/'supervisor.json').write_text(json.dumps(result,indent=2)+'\n')
        return result
