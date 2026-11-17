"""Read-only three-repository/pin checkpoint after fetching main refs."""
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
baseline = json.loads((HERE / 'baseline.json').read_text(encoding='utf-8'))


def git(directory, *args):
    result = subprocess.run(['rtk', 'proxy', 'git', *args], cwd=directory,
        stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding='utf-8', timeout=30, check=True)
    return result.stdout.strip()


report = dict(timestamp=datetime.now(UTC).isoformat(), main_refs_fetched=True,
    qualification='Repository state only; no runtime/default approval', repositories={}, pins={})
for name, directory in (
    ('nexus', ROOT),
    ('connector', ROOT.parent / 'okto-nexus-connector'),
    ('core', ROOT.parent / 'okto-nexus-connector-core'),
):
    report['repositories'][name] = dict(
        directory=str(directory), branch=git(directory, 'branch', '--show-current'),
        head=git(directory, 'rev-parse', 'HEAD'),
        main=git(directory, 'rev-parse', 'origin/main'),
        main_left_head_right=git(directory, 'rev-list', '--left-right', '--count', 'origin/main...HEAD'),
        working_tree=git(directory, 'status', '--porcelain=v1').splitlines())
for name, expected in baseline['pins'].items():
    actual = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
    report['pins'][name] = dict(expected=expected, actual=actual, matches=actual == expected)
assert all(item['matches'] for item in report['pins'].values())
assert not report['repositories']['connector']['working_tree']
assert not report['repositories']['core']['working_tree']
report['notes'] = [
    'Nexus contains the declared in-progress supplementary tests/evidence/docs; no uncommitted product source change.',
    'Core/Connector remain clean/read-only and use their existing branches/versions; no bump for an unimpacted repository.',
    'This records its generation HEAD before a subsequent evidence commit; it cannot name its own future commit.',
    'Fetching main updates remote references only; no checkout reset, merge or main rollback was performed.',
]
(HERE / 'repo-checkpoint-r7.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(dict(repositories={name: {key: value for key, value in row.items() if key != 'working_tree'}
    | {'working_tree_items': len(row['working_tree'])} for name, row in report['repositories'].items()}, pins_unchanged=True)))
