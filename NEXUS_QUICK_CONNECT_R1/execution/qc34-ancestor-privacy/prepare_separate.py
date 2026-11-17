"""Prepare independent cuts with only timed traceback instrumentation disabled."""
from pathlib import Path

HERE = Path(__file__).resolve().parent
runner = (HERE / 'run.py').read_text()
runner = runner.replace("own_cwd=root/'cwd'", "own_cwd=root/'separate-cwd'")
start = runner.index('nodes=')
end = runner.index('\nfor label,node in nodes:', start)
runner = runner[:start] + "nodes=[('registered-ancestor-focal','tests/quick_connect/test_ancestor_privacy.py::test_c13_registered_ancestor_does_not_expand_nested_cwd'),('privacy-observed-focal','tests/quick_connect/test_ancestor_privacy.py::test_d25_private_origin_does_not_enter_observed_logs_json_homes_or_sqlite')]" + runner[end:]
runner = runner.replace("'faulthandler_timeout=10'", "'faulthandler_timeout=0'")
runner = runner.replace("root/'result.json'", "root/'separate-result.json'")
(HERE / 'run_separate.py').write_text(runner, encoding='utf-8')
print('Prepared only. Original crash/result preserved; awaiting Root technical review.')
