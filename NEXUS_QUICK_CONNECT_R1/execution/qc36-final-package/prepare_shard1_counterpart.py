import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
original = HERE / 'installed_regression.py'
before = original.read_text(encoding='utf-8')
old = "    for name in ['CODEX_HOME','CLAUDE_CONFIG_DIR']:\n        directory=root/name.lower();directory.mkdir();env[name]=str(directory)\n"
new = """    codex_home=root/'codex_home';codex_home.mkdir();env['CODEX_HOME']=str(codex_home)
    claude_home=root/'claude_config_dir_intentionally_absent'
    assert not claude_home.exists()
    env['CLAUDE_CONFIG_DIR']=str(claude_home)
    (root/'reports/runner-env-precondition.json').write_text(json.dumps(dict(
        CODEX_HOME=dict(path=env['CODEX_HOME'],exists=codex_home.exists()),
        CLAUDE_CONFIG_DIR=dict(path=env['CLAUDE_CONFIG_DIR'],exists=claude_home.exists()),
        HOME=env['HOME'],USERPROFILE=env['USERPROFILE'],
        account_or_provider_values_inherited=False),indent=2)+'\\n')
"""
assert old in before
after = before.replace(old, new)
(HERE / 'installed_regression_shard1_counterpart.py').write_text(after, encoding='utf-8')
out = HERE / 'installed-shard-1-counterpart-proposal'
out.mkdir(exist_ok=True)
(out / 'runner.patch').write_text(''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True), fromfile='original/installed_regression.py', tofile='counterpart/installed_regression.py')), encoding='utf-8')
old_root = Path('C:/Users/jpamb/AppData/Local/Temp/nexus-qc36-installed-ubdefedx')
directory = old_root / 'claude_config_dir'
proof = {'original_runner_sha256': hashlib.sha256(original.read_bytes()).hexdigest(),
    'counterpart_runner_sha256': hashlib.sha256((HERE / 'installed_regression_shard1_counterpart.py').read_bytes()).hexdigest(),
    'original_code_lines': old, 'original_created_claude_directory': {'path': str(directory), 'exists': directory.is_dir(), 'children': len(list(directory.iterdir()))},
    'original_scope': 'Installed shard1 argv/result preserved in installed-shard-1; environment was constructed by these exact runner lines, not package.environment.',
    'counterpart': 'Only Claude environment path existence changes. Own HOME/USERPROFILE, allowlist, installed artifacts, test bodies, original runner and original failed cut remain unchanged.'}
assert directory.is_dir()
(out / 'read-only-cause.json').write_text(json.dumps(proof, indent=2), encoding='utf-8')
print(json.dumps(proof))
