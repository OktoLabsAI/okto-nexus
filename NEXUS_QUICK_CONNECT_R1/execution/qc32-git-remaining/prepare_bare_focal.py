"""Select the exact existing bare-repository node without changing its oracle."""
from pathlib import Path

HERE = Path(__file__).resolve().parent
runner = (HERE / 'run_derivative.py').read_text()
runner = runner.replace("own_cwd=root/'cwd'", "own_cwd=root/'bare-cwd'")
start = runner.index('nodes=')
end = runner.index('\nfor label,node in nodes:', start)
runner = runner[:start] + "nodes=[('bare-final','tests/quick_connect/test_git_remaining.py::test_real_bare_repository_has_explicit_directory_fallback_not_origin_identity')]" + runner[end:]
needle = ",' -k'"  # no shell construction: replace the literal argv fragment below
runner = runner.replace(",'-k','test_real_repository_help_and_plan_never_execute_git or test_bare_repository_uses_explicit_fallback_not_its_origin_identity'", '')
runner = runner.replace("root/'result.json'", "root/'bare-result.json'")
(HERE / 'run_bare_focal.py').write_text(runner, encoding='utf-8')
print('Prepared exact bare node; fixture source unchanged.')
