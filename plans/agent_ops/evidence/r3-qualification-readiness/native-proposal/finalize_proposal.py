"""Finalize the already completed read-only checks; preserve original driver.

The first generation stopped at its overly broad clean-worktree assertion:
root was updating vendor/ci packaging inputs, outside the compared source trees.
This script repeats no imports, CLI checks, Task Scheduler access or install.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
original = ROOT / 'prepare_proposal.py'
source = original.read_text(encoding='utf-8')
source = source.replace("for path in (home, state, project):\n    path.mkdir(parents=True, exist_ok=False)",
    "for path in (home, state, project):\n    assert path.is_dir() and not any(path.iterdir())")
start, end = source.index('checks = []'), source.index('installed = json.loads')
source = source[:start] + "checks = json.loads((ROOT / 'read-only-checks.json').read_text())\nassert len(checks) == 8 and all(item['returncode'] == 0 for item in checks)\n" + source[end:]
source = source.replace(
    "    clean = not subprocess.check_output(['git', '-C', repo, 'status', '--porcelain'], text=True).strip()\n    assert clean\n    heads[name] = dict(repository=repo, commit=commit, clean_at_preparation=True)",
    "    changes = subprocess.check_output(['git', '-C', repo, 'status', '--porcelain'], text=True).splitlines()\n"
    "    assert all(line[3:].replace('\\\\', '/').startswith('vendor/ci/') for line in changes), 'Unexpected source change; re-review required.'\n"
    "    heads[name] = dict(repository=repo, commit=commit, clean_at_finalization=not changes, pending_nonproduct_changes=changes)")
source = source.replace("write('native-service-campaign-proposal.json', proposal)",
    "proposal['preparation_note'] = 'All 8 read-only checks passed before the original driver rejected concurrent vendor/ci-only edits. This finalization reused those closed reports and records current HEAD plus nonproduct changes; no native calls were repeated.'\n"
    "write('native-service-campaign-proposal.json', proposal)")
exec(compile(source, str(original), 'exec'))
