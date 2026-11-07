"""Record changed-file lint and compare existing diagnostics to HEAD."""
from collections import Counter
import json
from pathlib import Path
import subprocess

base = Path(__file__).parent
paths = json.loads((base / 'changed-paths.json').read_text())
results = {}
for directory, changed in paths.items():
    repo = Path(directory)
    files = [name for name in changed if name.endswith('.py')]
    run = subprocess.run(['ruff', 'check', '--output-format', 'json', *files], cwd=repo,
                         capture_output=True, text=True)
    assert run.returncode in (0, 1), run.stderr
    current = json.loads(run.stdout)
    baseline = []
    for name in files:
        old = subprocess.run(['git', 'show', 'HEAD:' + name], cwd=repo, capture_output=True, text=True)
        if old.returncode:
            continue
        lint = subprocess.run(['ruff', 'check', '--output-format', 'json', '--stdin-filename', name, '-'],
                              cwd=repo, input=old.stdout, capture_output=True, text=True)
        assert lint.returncode in (0, 1), lint.stderr
        baseline.extend(json.loads(lint.stdout))
    def key(item):
        return (str(Path(item['filename']).relative_to(repo)), item['code'], item['message'])
    introduced = Counter(map(key, current)) - Counter(map(key, baseline))
    assert not introduced, introduced
    diff = subprocess.run(['git', 'diff', '--check'], cwd=repo, capture_output=True, text=True)
    assert diff.returncode == 0, diff.stdout + diff.stderr
    results[repo.name] = dict(files=files, current_diagnostics=len(current), baseline_diagnostics=len(baseline),
        introduced_diagnostics=[], remaining=current, diff_check_passed=True,
        baseline_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip())
(base / 'static-checks.json').write_text(json.dumps(results, indent=2))
print(json.dumps({k: {name: v[name] for name in ('current_diagnostics', 'baseline_diagnostics',
    'introduced_diagnostics', 'diff_check_passed')} for k, v in results.items()}, indent=2))
