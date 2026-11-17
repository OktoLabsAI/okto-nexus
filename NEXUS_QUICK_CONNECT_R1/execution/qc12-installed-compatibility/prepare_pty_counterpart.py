"""Prepare the explicitly authorized non-TTY exclusion counterpart, not PTY QA."""
from pathlib import Path

HERE = Path(__file__).resolve().parent
runner = (HERE / 'run_git_counterpart.py').read_text(encoding='utf-8')
runner = runner.replace("root/'counterpart-cwd'", "root/'pty-counterpart-cwd'")
runner = runner.replace("nodes=[('counterpart-git','tests/quick_connect/test_git_project_hint.py')]",
    "nodes=[('counterpart-pty','tests/quick_connect/test_quick_connect_pty.py')]")
runner = runner.replace("root/'counterpart-git-result.json'", "root/'counterpart-pty-result.json'")
runner = runner.replace('def pytest_sessionstart(session):',
    "def pytest_sessionstart(session):\n    assert sys.stdin.isatty() is False, 'Non-TTY PIPE precondition was not met'")
runner = runner.replace('dict(origins=origins,prefix=sys.prefix,sys_path=sys.path)',
    'dict(origins=origins,prefix=sys.prefix,sys_path=sys.path,stdin_isatty=sys.stdin.isatty(),stdin_mode="PIPE_closed")')
runner = runner.replace('stdin=subprocess.DEVNULL,stdout=log', 'stdin=subprocess.PIPE,stdout=log')
runner = runner.replace('        known[process.pid]=Owned(process.pid)',
    '        process.stdin.close()\n        known[process.pid]=Owned(process.pid)')
(HERE / 'run_pty_counterpart.py').write_text(runner, encoding='utf-8')
print('Prepared non-TTY counterpart only; run after Git counterpart exits.')
