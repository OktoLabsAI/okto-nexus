"""Compare scoped default Ruff diagnostics with the retained analysis baseline."""
from collections import Counter
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent / 'static-checks'
BASE = 'f28a31a22436c366a4c8dbdf5e3b250d606a61be'


def call(args, **kwargs):
    return subprocess.run(args, cwd=ROOT, stdin=None if 'input' in kwargs else subprocess.DEVNULL,
                          capture_output=True, encoding='utf-8', **kwargs)


def lint(path, contents):
    result = call(['rtk', 'proxy', 'uvx', '--offline', 'ruff', 'check', '--no-fix',
                   '--output-format', 'json', '--stdin-filename', path, '-'], input=contents)
    assert result.returncode in (0, 1), result.stderr
    return json.loads(result.stdout)


def main():
    names = set(call(['rtk', 'proxy', 'git', 'diff', '--name-only', BASE, '--', 'src', 'tests/home_states', 'tools']).stdout.splitlines())
    names.update(call(['rtk', 'proxy', 'git', 'ls-files', '--others', '--exclude-standard', '--',
                       'src', 'tests/home_states', 'tools']).stdout.splitlines())
    names = sorted(name for name in names if name.endswith('.py') and (ROOT / name).is_file())
    checks = {}
    for name in names:
        contents = (ROOT / name).read_text(encoding='utf-8')
        baseline = call(['rtk', 'proxy', 'git', 'show', BASE + ':' + name])
        before = lint(name, baseline.stdout) if baseline.returncode == 0 else []
        after = lint(name, contents)
        old = Counter(row['code'] for row in before)
        current = Counter(row['code'] for row in after)
        checks[name] = {'sha256': hashlib.sha256(contents.encode()).hexdigest(),
                        'baseline': before, 'current': after,
                        'increased_rule_counts': dict(current - old)}
    HERE.mkdir(exist_ok=True)
    report = {'at': datetime.now(UTC).isoformat(), 'baseline': BASE,
              'version': call(['rtk', 'proxy', 'uvx', '--offline', 'ruff', '--version']).stdout.strip(),
              'scope': 'Changed/new Python product, home_states tests and tools; default repository configuration',
              'checks': checks,
              'limitations': ['Diagnostic count comparison is not the full repository lint gate or functional testing.']}
    (HERE / 'ruff.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    increased = {name: row['increased_rule_counts'] for name, row in checks.items() if row['increased_rule_counts']}
    print(json.dumps({'files': len(checks), 'increased': increased}))
    raise SystemExit(bool(increased))


if __name__ == '__main__':
    main()
