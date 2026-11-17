"""Prepare the authorized nine-case composed installed Git/CLI cut."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

HERE = Path(__file__).resolve().parent
previous = Path(json.loads((HERE / 'allocation.json').read_text())['root'])
root = Path(tempfile.mkdtemp(prefix='nexus-qc-git-cli-installed-')).resolve()
(HERE / 'git-integration-allocation.json').write_text(json.dumps(dict(root=str(root)), indent=2), encoding='utf-8')
shutil.copytree(previous / 'after', root / 'after', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
for filename in ('source-pins.json', 'pytest.ini'):
    shutil.copyfile(previous / filename, root / filename)
proposal = json.loads((HERE / 'git-integration-proposal.json').read_text())
source = Path(proposal['test_file'])
assert hashlib.sha256(source.read_bytes()).hexdigest() == proposal['sha256']
target = root / 'after/tests/quick_connect/test_git_cli_integration.py'
shutil.copyfile(source, target)
(root / 'extra-test-pin.json').write_text(json.dumps(dict(original=str(source),
    copied=str(target), sha256=proposal['sha256']), indent=2), encoding='utf-8')
runner = (HERE / 'run.py').read_text(encoding='utf-8')
runner = runner.replace("HERE/'allocation.json'", "HERE/'git-integration-allocation.json'")
start = runner.index('package=Path(json.loads')
runner = runner[:start] + "own_cwd=root/'cwd'\nown_cwd.mkdir(exist_ok=False)\n" + runner[start:]
start = runner.index('nodes=')
end = runner.index('\nfor label,node in nodes:', start)
runner = runner[:start] + "nodes=[('git-cli-composed','tests/quick_connect/test_git_cli_integration.py')]" + runner[end:]
runner = runner.replace('cwd=str(root)', 'cwd=str(own_cwd)').replace('cwd=root,', 'cwd=own_cwd,')
runner = runner.replace('stdin=subprocess.DEVNULL,stdout=log', 'stdin=subprocess.PIPE,stdout=log')
runner = runner.replace('        known[process.pid]=Owned(process.pid)', '        process.stdin.close()\n        known[process.pid]=Owned(process.pid)')
runner = runner.replace('def pytest_sessionstart(session):',
    "def pytest_sessionstart(session):\n    assert sys.stdin.isatty() is False, 'Non-TTY PIPE precondition was not met'")
runner = runner.replace('dict(origins=origins,prefix=sys.prefix,sys_path=sys.path)',
    'dict(origins=origins,prefix=sys.prefix,sys_path=sys.path,stdin_isatty=sys.stdin.isatty(),stdin_mode="PIPE_closed")')
runner = runner.replace("env['QC_DERIVATIVE_OUTPUT']=str(out)",
    "env['QC_DERIVATIVE_OUTPUT']=str(out)\n    assert not Path(env['TMP']).resolve().is_relative_to(own_cwd.resolve())\n    assert not own_cwd.resolve().is_relative_to(Path(env['TMP']).resolve())")
(HERE / 'run_git_integration.py').write_text(runner, encoding='utf-8')
print(json.dumps(dict(root=str(root), extra_test_sha256=proposal['sha256'])))
