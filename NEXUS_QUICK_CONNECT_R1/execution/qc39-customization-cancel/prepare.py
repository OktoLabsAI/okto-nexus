import ast
from pathlib import Path

HERE = Path(__file__).resolve().parent
source = (HERE.parent / 'qc38-final-source-check/run.py').read_text(encoding='utf-8')
tree = ast.parse(source)
node = next(n for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'cases' for t in n.targets))
lines = source.splitlines(keepends=True)
lines[node.lineno - 1:node.end_lineno] = ["cases = [('customization-cancel', 'tests/quick_connect/test_qc35_review_cancel.py', [])]\n"]
source = ''.join(lines).replace("prefix='nexus-qc38-source-'", "prefix='nexus-qc39-source-'")
source = source.replace("'-v', '-s', '--tb=short'", "'-v', '-s', '-o', 'faulthandler_timeout=0', '--tb=short'")
(HERE / 'run_red.py').write_text(source, encoding='utf-8')
print('Prepared SOURCE_ONLY red runner; eight cases, no process started.')
