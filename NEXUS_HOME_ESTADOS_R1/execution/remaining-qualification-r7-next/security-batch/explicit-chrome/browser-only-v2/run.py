"""Prepared browser-only diagnostic; requires its own new Root gate."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

import psutil

HERE=Path(__file__).resolve().parent
BASE=HERE.parent.parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def check(gate_path):
    gate=json.loads(gate_path.read_text())
    manifest=json.loads((HERE/'manifest.json').read_text())
    assert gate.get('approved') is True and gate.get('approved_by')=='root'
    assert gate['kind']=='BROWSER_ONLY_ABOUT_BLANK' and gate['owner_seconds']==90
    assert gate['manifest_sha256']==sha(HERE/'manifest.json')
    assert gate['allow_own_containment'] is True
    import re
    assert re.fullmatch(r'hst-browser-only-[a-z0-9-]{1,70}',gate['cut_id'])
    assert not (HERE/('attempt-'+gate['cut_id']+'.json')).exists()
    for path,pin in manifest['input_pins'].items():
        assert sha(path)==pin,path
    tool=Path(manifest['node_modules']).resolve()
    actual={path.relative_to(tool).as_posix():sha(path)
        for name in ('@playwright/cli','playwright','playwright-core')
        for path in (tool/name).rglob('*') if path.is_file()}
    assert actual==manifest['cli_payload_pins'], 'Exact CLI closure drift'
    assert Path(manifest['entry']).resolve().is_relative_to(tool)
    assert json.loads((HERE/'playwright-cli.json').read_text())==manifest['browser_config']
    return gate,manifest


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--gate',type=Path,required=True)
    args=parser.parse_args()
    gate,manifest=check(args.gate)  # No allocation/import of controller before gate.
    gate_before=sha(args.gate)
    manifest_before=sha(HERE/'manifest.json')
    with (HERE/('attempt-'+gate['cut_id']+'.json')).open('x') as stream:
        stream.write(json.dumps({'gate_sha256':sha(args.gate),'manifest_sha256':sha(HERE/'manifest.json')})+'\n')
    root=Path(tempfile.mkdtemp(prefix='nexus-hst-browser-diagnostic-')).resolve()
    assert root.parent==Path(tempfile.gettempdir()).resolve()
    (root/'cwd').mkdir()
    controls=module('browser_only_commands',BASE/'run.py')
    lifecycle=module('browser_only_environment',BASE.parents[1]/'browser-hst/containment.py')
    assert not any(name.startswith(('okto_nexus','nexus_connector_core','okto_nexus_connector')) for name in sys.modules)
    env=lifecycle.environment(root)
    env.update(NO_UPDATE_NOTIFIER='1',DEBUG='pw:browser*,pw:api')
    assert env['PATH']==''
    configuration=root/'playwright-cli.json'
    shutil.copyfile(HERE/'playwright-cli.json',configuration)
    assert sha(configuration)==manifest['input_pins'][str(HERE/'playwright-cli.json')]
    deadline=time.monotonic()+90
    owner=controls.Commands(root,env,deadline)
    rtk=shutil.which('rtk')
    assert rtk
    prefix=[rtk,'proxy',manifest['node'],manifest['entry'],'--session='+gate['cut_id']]
    phases=[]
    failure=None
    opened=False
    result=None
    print(json.dumps({'phase':'ALLOCATED_BROWSER_ONLY','root':str(root),'server_started':False}),flush=True)
    def command(name,*arguments,timeout=20,cleanup=False):
        print(json.dumps({'phase':name.upper()+'_START'}),flush=True)
        value=owner.run(name,prefix+list(arguments),timeout=timeout,cleanup=cleanup)
        phases.append(name)
        print(json.dumps({'phase':name.upper()+'_COMPLETE'}),flush=True)
        return value
    try:
        command('open','open','about:blank','--browser=chrome',
            '--profile='+str(root/'browser-profile'),'--config='+str(configuration),timeout=50)
        opened=True
        body=root/'about-blank.js'
        body.write_text("async page=>({status:'PASS_ABOUT_BLANK_ONLY',url:page.url(),title:await page.title(),pages:page.context().pages().length})")
        output=command('inspect','run-code','--filename='+str(body),timeout=10)
        result=controls.cli_result(output)
        assert result['status']=='PASS_ABOUT_BLANK_ONLY' and result['url']=='about:blank'
    except BaseException as error:
        failure={'type':type(error).__name__,'message':str(error)}
    finally:
        if opened:
            try: command('close','close',timeout=10,cleanup=True)
            except BaseException as error:
                failure=failure or {'type':type(error).__name__,'message':'Close command failed'}
        end=time.monotonic()+5
        while owner.remaining() and time.monotonic()<end:
            time.sleep(.1)
        containment=owner.contain() if owner.remaining() else {'forced_births':[],'remaining':[]}
        after={path:sha(path) for path in manifest['input_pins']}
        tool=Path(manifest['node_modules'])
        after_cli={path.relative_to(tool).as_posix():sha(path)
            for name in ('@playwright/cli','playwright','playwright-core')
            for path in (tool/name).rglob('*') if path.is_file()}
        immutable=(after==manifest['input_pins'] and after_cli==manifest['cli_payload_pins']
            and sha(configuration)==manifest['input_pins'][str(HERE/'playwright-cli.json')]
            and gate_before==sha(args.gate) and manifest_before==sha(HERE/'manifest.json'))
        loaded=[name for name in sys.modules if name.startswith(('okto_nexus','nexus_connector_core','okto_nexus_connector'))]
        pids={item['pid'] for item in owner.known.values()}
        listeners=[{'pid':item.pid,'port':item.laddr.port} for item in psutil.net_connections(kind='tcp')
                   if item.pid in pids and item.status=='LISTEN']
        report={'status':'PASS_BROWSER_ONLY' if not failure and immutable and not containment['forced_births'] and not containment['remaining'] and not loaded and not listeners else 'FAIL_OR_INCONCLUSIVE_PRESERVED',
            'root':str(root),'kind':gate['kind'],'cut_id':gate['cut_id'],'gate_sha256':gate_before,
            'manifest_sha256':manifest_before,'phases':phases,'commands':owner.commands,
            'failure':failure,'result':result,'immutable':immutable,'cleanup':containment,
            'known_births':list(owner.known.values()),'remaining_listeners':listeners,
            'product_modules_loaded':loaded,'server_started':False,'native_peer_started':False,
            'provider_invocations':0,'npx_used':False,'npm_used':False,'NO_UPDATE_NOTIFIER':'1',
            'DEBUG':'pw:browser*,pw:api','owner_seconds':90,
            'scope':'About:blank startup/inspection/close only; no Home/security/app/browser performance claim',
            'sampling_limit':'Known ancestry plus own-root/birth scan; no enumeration claim for every short-lived child'}
        (root/'browser-only-private.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps({'phase':'FINISHED','root':str(root),'status':report['status'],
            'failure_type':failure['type'] if failure else None,'remaining':len(containment['remaining'])}),flush=True)
    return 0 if report['status']=='PASS_BROWSER_ONLY' else 1


if __name__=='__main__':
    raise SystemExit(main())
