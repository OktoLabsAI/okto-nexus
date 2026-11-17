"""Preserve the original run and prepare its CWD/TMP sibling counterpart."""
from pathlib import Path

HERE = Path(__file__).resolve().parent
runner = (HERE / 'run.py').read_text(encoding='utf-8')
marker = "package=Path(json.loads"
start = runner.index(marker)
runner = runner[:start] + "own_cwd=root/'counterpart-cwd'\nown_cwd.mkdir(exist_ok=False)\n" + runner[start:]
start = runner.index('nodes=')
end = runner.index('\nfor label,node in nodes:', start)
runner = runner[:start] + "nodes=[('counterpart-git','tests/quick_connect/test_git_project_hint.py')]" + runner[end:]
runner = runner.replace('cwd=str(root)', 'cwd=str(own_cwd)').replace('cwd=root,', 'cwd=own_cwd,')
runner = runner.replace("root/'result.json'", "root/'counterpart-git-result.json'")
runner = runner.replace("env['QC_DERIVATIVE_OUTPUT']=str(out)",
    "env['QC_DERIVATIVE_OUTPUT']=str(out)\n    assert not Path(env['TMP']).resolve().is_relative_to(own_cwd.resolve())\n    assert not own_cwd.resolve().is_relative_to(Path(env['TMP']).resolve())")
(HERE / 'run_git_counterpart.py').write_text(runner, encoding='utf-8')
print('Prepared only; wait until original QC12 cuts finish.')
