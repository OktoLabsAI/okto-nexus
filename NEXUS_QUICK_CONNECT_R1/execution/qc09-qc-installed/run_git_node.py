"""Counterpart of the one runner-cwd fixture failure, corrected isolation only."""
import json
from pathlib import Path
import tempfile

import run_qc as scope

own = Path(tempfile.mkdtemp(prefix='nexus-qc09-git-cwd-counterpart-'))
scope.engine.PLUGIN += scope.AUDIT.replace('SOURCE_VALUE', repr(str(scope.ROOT / 'src')))
node = 'tests/quick_connect/test_git_project_hint.py::test_path_search_has_entry_and_time_budgets'
output, result = scope.engine.execute(own / 'run', [node])
report = dict(node=node, own_root=str(own), output=str(output), result=result,
    environment_delta='pytest cwd is own/run/cwd, sibling to own/run/tmp; fake Git installation is outside invocation cwd',
    scope='Exact same installed product and source test; no Root source/test/prefix changes')
(scope.HERE / 'git-cwd-counterpart.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
print(json.dumps(dict(exit_code=result['exit_code'], output=str(output))))
raise SystemExit(result['exit_code'])
