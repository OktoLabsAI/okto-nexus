"""Prepare an external installed-only copy and bounded eight-case campaign."""
from pathlib import Path
import json
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
previous = HERE.parent / 'qc12-installed-compatibility/prepare.py'
text = previous.read_text(encoding='utf-8')
text = text[:text.index("runner = (HERE.parent")]
text = text.replace("prefix='nexus-qc12-installed-'", "prefix='nexus-qc15-choice-'")
exec(compile(text, str(HERE/'prepare.py'), 'exec'))
import shutil
shutil.copyfile(HERE/'test_cli_choices.py', root/'after/tests/execution_r4/test_qc15_cli_choices.py')
runner = (HERE.parent/'qc09-review/run_derivative.py').read_text(encoding='utf-8')
runner = runner.replace("HERE/'derivative-allocation.json'", "HERE/'allocation.json'")
runner = runner.replace("HERE.parent/'qc08-package/allocation.json'", "HERE.parent/'qc11-package/allocation.json'")
start = runner.index("nodes=[('mutable-feature'")
end = runner.index('\nfor label,node in nodes:', start)
runner = runner[:start] + "nodes=[('choices','tests/execution_r4/test_qc15_cli_choices.py')]" + runner[end:]
runner = runner.replace("'-v','-s','--tb=short'", "'-v','-s','-x','--tb=short'")
runner = runner.replace('deadline_seconds=60', 'deadline_seconds=180').replace('deadline=time.monotonic()+60', 'deadline=time.monotonic()+180')
runner = runner.replace("due=now>=deadline or failed_at is not None and now-failed_at>=15", "due=now>=deadline")
runner = runner.replace("env['PATH']=str(out/'empty-path')", "env['PATH']=';'.join([str(package/'venv/Scripts'),r'C:/Python313',r'C:/Windows/System32',r'C:/Windows',r'C:/Program Files/nodejs',r'C:/Program Files/Git/cmd'])\n    env.update(GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_SYSTEM=os.devnull,GIT_CONFIG_GLOBAL=os.devnull,GIT_TERMINAL_PROMPT='0')")
runner = runner.replace("command=[rtk,'proxy',str(python)", "command=[str(python)")
runner = runner.replace("record=dict(label=label", "(out/'cwd').mkdir()\n    record=dict(label=label")
runner = runner.replace("cwd=str(root),deadline", "cwd=str(out/'cwd'),deadline")
runner = runner.replace("Popen(command,cwd=root", "Popen(command,cwd=out/'cwd'")
runner = runner.replace("stdin=subprocess.DEVNULL", "stdin=subprocess.PIPE")
runner = runner.replace("known[process.pid]=Owned(process.pid)", "process.stdin.close()\n        known[process.pid]=Owned(process.pid)")
runner = runner.replace("before=payload()", "assert hashlib.sha256((package/'artifacts/okto_nexus-0.3.6-py3-none-any.whl').read_bytes()).hexdigest()=='a36e448c80a8190c7e8c92d81ea5a251c4bdf7e370eca0f0b395a5ad29e36cc6'\nbefore=payload()")
# Guard both session boundaries, and do not copy module caches back to evidence.
runner = runner.replace("@pytest.hookimpl(hookwrapper=True)", "def pytest_sessionfinish(session, exitstatus):\n    origins={name:importlib.util.find_spec(name).origin for name in ('okto_nexus','nexus_connector_core','okto_nexus_connector')}\n    invalid={name:getattr(module,'__file__',None) for name,module in list(sys.modules.items()) if name.startswith(('okto_nexus','nexus_connector_core','okto_nexus_connector')) and getattr(module,'__file__',None) and not pathlib.Path(module.__file__).resolve().is_relative_to(PREFIX)}\n    assert not invalid,invalid\n    (OUT/'origins-finish.json').write_text(json.dumps(dict(origins=origins,invalid=invalid),indent=2))\n\n@pytest.hookimpl(hookwrapper=True)")
(HERE/'run.py').write_text(runner, encoding='utf-8')
print(json.dumps(dict(root=str(root),cases=8,src_present=(root/'after/src').exists())))
