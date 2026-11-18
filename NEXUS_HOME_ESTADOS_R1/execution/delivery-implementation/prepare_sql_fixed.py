import ast
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent
shutil.copyfile(HERE / 'final-allocation.json', HERE / 'sql-error-allocation.json')
source = (HERE / 'run_final.py').read_text(encoding='utf-8')
tree = ast.parse(source)
node = next(n for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'cases' for t in n.targets))
lines = source.splitlines(keepends=True)
cases = [('verification', 'tests/home_states/test_verification_proof.py', []),
    ('legacy-result-artifacts', 'tests/home_evolution/test_home_result_artifact_grouping.py', []),
    ('legacy-home-queries', 'tests/home_evolution/test_home_queries.py', [])]
lines[node.lineno - 1:node.end_lineno] = ['cases = ' + repr(cases) + '\n']
source = ''.join(lines).replace("HERE / 'final-allocation.json'", "HERE / 'sql-fixed-allocation.json'")
(HERE / 'run_sql_fixed.py').write_text(source, encoding='utf-8')
print('Prepared only SQL-affected focal regressions; prior failures retained.')
