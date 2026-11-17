import hashlib
import importlib.util
import json
import os
import platform
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
OWN = Path(__file__).resolve().parent
PYTHON = OWN / 'venv/Scripts/python.exe'
spec = importlib.util.spec_from_file_location('ci_runner_metadata', ROOT / 'tools/ci_installed.py')
ci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ci)
ENV = {k:v for k,v in os.environ.items() if k.upper() not in ('PYTHONPATH','PYTHONHOME','OKTO_NEXUS_HOME','OKTO_NEXUS_DB_PATH')}
ENV = {k:v for k,v in ENV.items() if not k.upper().startswith(('OPENAI','ANTHROPIC','CLAUDE','CODEX','OKTO_NEXUS','NEXUS_CONNECTOR'))
       and not any(part in k.upper() for part in ('API_KEY','ACCESS_TOKEN','AUTH_TOKEN','PASSWORD','SECRET'))}
ENV['PYTHONIOENCODING'] = 'utf-8'
ENV['PYTHONUTF8'] = '1'

def connector_inputs():
    root=ROOT.parent/'okto-nexus-connector'
    paths=[root/'pyproject.toml',root/'uv.lock']
    for directory in ('src','tests'):
        paths.extend(p for p in (root/directory).rglob('*') if p.is_file() and p.suffix in ('.py','.json','.sql') and '__pycache__' not in p.parts)
    return {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths) if p.is_file()}

def run(name, args):
    command = ['rtk', 'proxy', *map(str,args)]
    record = {'command':command,'cwd':str(OWN),'started_at':datetime.now(timezone.utc).isoformat()}
    with (OWN / (name+'.log')).open('w',encoding='utf-8') as output:
        result = subprocess.run(command,cwd=OWN,env=ENV,stdout=output,stderr=subprocess.STDOUT)
    record.update(exit_code=result.returncode,ended_at=datetime.now(timezone.utc).isoformat())
    (OWN / (name+'.json')).write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(record),flush=True)
    return result.returncode

if __name__ == '__main__':
    action = sys.argv[1]
    build = OWN / (sys.argv[2] if len(sys.argv)>2 else 'nexus')
    suffix = '' if build.name=='nexus' else '-final'
    ci_output = OWN / ('ci'+suffix)
    if action == 'snapshot':
        data={'at':datetime.now(timezone.utc).isoformat(),'python':sys.version,'os':platform.platform(),
              'inputs':ci.input_hashes(),'connector_inputs':connector_inputs(),'parent_environment_pythonpath_removed':True}
        (OWN / 'before.json').write_text(json.dumps(data,indent=2)+'\n')
    elif action in ('install','smoke','test','related-focal','connector-test','reinstall'):
        wheel = next(build.glob('*.whl'))
        if action=='reinstall':
            sys.exit(run(action+suffix,[PYTHON,'-I','-m','pip','install','--no-deps','--force-reinstall',wheel]))
        selected_action='test' if action in ('connector-test','related-focal') else action
        if action=='related-focal':ci_output=OWN/'ci-related-focal'
        args=[PYTHON,'-I',ROOT/'tools/ci_installed.py',selected_action,'--wheel',wheel,'--output',OWN/'ci-connector-final' if action=='connector-test' else ci_output]
        if action == 'test':
            paths=[str(p.relative_to(ROOT)).replace('\\','/') for p in sorted((ROOT/'tests/UI_simplification').glob('test_*.py')) if p.name!='test_fixtures.py']
            paths += ['tests/execution_r4/'+name+'.py' for name in (
                'test_connection_choices','test_connection_picker','test_canonical_connection_choices',
                'test_canonical_connection_discovery','test_connection_catalog','test_connection_catalog_remote',
                'test_terminal_session_picker','test_terminal_multi_harness','test_connection_setup',
                'test_connection_setup_recovery','test_connection_continuity','test_remote_setup_integration',
                'test_daemon_startup')]
            args += ['--tests',*paths]
        if action=='connector-test':
            args += ['--tests','../okto-nexus-connector/tests/unit/test_connection_choices.py',
                '../okto-nexus-connector/tests/unit/test_connect_reuse.py']
        if action=='related-focal':
            args += ['--tests','tests/UI_simplification/test_entry_related.py::test_attention_preview_and_pages_preserve_five_canonical_questions',
                'tests/UI_simplification/test_entry_related.py::test_results_preview_and_pages_preserve_five_canonical_deliveries']
        sys.exit(run(action+suffix,args))
    elif action in ('live','live-http'):
        sys.exit(run(('live-mcp' if action=='live' else 'live-http')+suffix,[PYTHON,'-I',ROOT/'scripts/live_client.py']))
    elif action == 'twine':
        artifacts=[*sorted(build.glob('*.whl')),*sorted(build.glob('*.tar.gz')),
                   *sorted((OWN/'connector').glob('*.whl')),*sorted((OWN/'connector').glob('*.tar.gz'))]
        sys.exit(run('twine'+suffix,['uvx','twine','check',*artifacts]))
    elif action == 'after':
        baseline=json.loads((OWN/'before.json').read_text())
        before=baseline['inputs']
        after=ci.input_hashes()
        changed=[p for p in sorted(before.keys()|after.keys()) if before.get(p)!=after.get(p)]
        connector_after=connector_inputs()
        connector_before=baseline.get('connector_inputs',{})
        connector_changed=[p for p in sorted(connector_before.keys()|connector_after.keys()) if connector_before.get(p)!=connector_after.get(p)]
        report={'changed_inputs':changed,'after':after,'changed_connector_inputs':connector_changed,'connector_after':connector_after,
                'artifacts':{str(p.relative_to(OWN)):hashlib.sha256(p.read_bytes()).hexdigest() for d in ('connector','nexus','nexus-final') for p in (OWN/d).glob('*') if p.suffix in ('.whl','.gz')}}
        (OWN/'after.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps({'changed_inputs':changed,'artifacts':report['artifacts']},indent=2))
