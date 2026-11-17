import ast
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
source = (REPO / 'NEXUS_QUICK_CONNECT_R1/execution/qc39-customization-cancel/run_green.py').read_text(encoding='utf-8')
tree = ast.parse(source)
case = next(n for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'cases' for t in n.targets))
lines = source.splitlines(keepends=True)
lines[case.lineno - 1:case.end_lineno] = ["cases = [('domain', 'tests/home_states/test_delivery_semantics.py', []), ('verification', 'tests/home_states/test_verification_proof.py', [])]\n"]
source = ''.join(lines).replace("prefix='nexus-qc39-source-'", "prefix='nexus-hst-delivery-source-'")
source = source.replace("str(REPO/'tests/execution_r4'),", "str(REPO/'tests'), str(REPO/'tests/execution_r4'),")
source = source.replace("HERE / 'green-allocation.json'", "HERE / 'allocation.json'")
(HERE / 'run.py').write_text(source, encoding='utf-8')
print('Prepared finite SOURCE_ONLY domain + real verification focals.')
