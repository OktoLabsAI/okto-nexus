"""Two focal fixture/oracle corrections; preserve six-case antecedent."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

HERE = Path(__file__).resolve().parent
old = Path(json.loads((HERE / 'allocation.json').read_text())['root'])
assert (old / 'result.json').exists()
for name in ('allocation.json', 'run.py'):
    shutil.copyfile(HERE / name, HERE / name.replace('.', '-antecedent.', 1))
root = Path(tempfile.mkdtemp(prefix='nexus-qc17-corrected-'))
shutil.copytree(old / 'after', root / 'after', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
for name in ('pytest.ini', 'source-pins.json'):
    shutil.copyfile(old / name, root / name)
test = root / 'after/tests/quick_connect/test_quick_connect_project_scenarios.py'
text = test.read_text().replace('from pathlib import Path\n', 'from pathlib import Path\nimport json\n')
text = text.replace("        result = invoke(c, capsys, tokens)\n", """        if tokens == ['connect', '--json']:
            from okto_nexus.adapters.inbound.cli import main
            # This is the real bare grammar. quick_cli.run normally adds
            # --provider-home, a deliberate legacy selector, so do not use it.
            code = main.main([*tokens, '--home', str(c.home)])
            captured = capsys.readouterr()
            assert code == 0, captured.out + captured.err
            result = json.loads(captured.out)
        else:
            result = invoke(c, capsys, tokens)
""")
needle = "    assert result['quick_connect']['canonical_reference'] == second['quick_connect']['canonical_reference']\n    assert result['quick_connect']['project_root'] == str(root_b)"
replacement = """    assert result['quick_connect']['status'] == 'planned'
    assert 'canonical_reference' not in result['quick_connect']
    shortcuts = list((c.home / 'terminal/profiles').glob('canonical-*.json'))
    assert len(shortcuts) == 1
    shortcut = json.loads(shortcuts[0].read_text())
    assert shortcut['selection']['project'] == str(root_b)
    assert shortcut['selection']['binding_id'] == second['binding_id']
    assert shortcut['selection']['workspace_id'] == second['workspace_id']
    assert canonical_snapshot(c) == before
    # Explicit observation after plan, same selection; no execution permission
    # or Test is inferred from the planned envelope.
    assert c.run(['connect', 'codex', 'Project B', '--no-chat']) == 0
    capsys.readouterr()
    assert prompts == ['Use approved folder: ', 'Choice: '] * 2
    result = displayed[-1]
    assert result['quick_connect']['canonical_reference'] == second['quick_connect']['canonical_reference']
    assert result['quick_connect']['project_root'] == str(root_b)"""
assert needle in text
text = text.replace(needle, replacement)
test.write_text(text, encoding='utf-8')
src = (HERE / 'run.py').read_text()
start = src.index('nodes=[')
end = src.index('\nfor label,node in nodes:', start)
functions = ['test_c01_mapped_cwd_bare_and_harness_resume_exact_reference',
             'test_c09_other_mapped_project_root_requires_explicit_tty_choice']
src = src[:start] + 'nodes=' + repr([(f.split('_')[1], 'tests/quick_connect/' + test.name + '::' + f) for f in functions]) + src[end:]
(HERE / 'run.py').write_text(src, encoding='utf-8')
(HERE / 'allocation.json').write_text(json.dumps(dict(root=str(root), external_test=str(test),
    sha256=hashlib.sha256(test.read_bytes()).hexdigest(), executed=False,
    changes=['Bare main excludes helper-added legacy --provider-home.',
             'Plan envelope checked as planned; separate explicit non-plan resume checks canonical reference.']), indent=2) + '\n')
print(json.dumps(dict(root=str(root), sha256=hashlib.sha256(test.read_bytes()).hexdigest())))
