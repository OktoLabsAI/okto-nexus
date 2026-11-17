import ast
from pathlib import Path

HERE = Path(__file__).resolve().parent
source = (HERE / 'run_final.py').read_text(encoding='utf-8')
tree = ast.parse(source)
node = next(n for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'cases' for t in n.targets))
lines = source.splitlines(keepends=True)
cases = [('domain', 'tests/home_states/test_delivery_semantics.py', []),
    ('verification', 'tests/home_states/test_verification_proof.py', []),
    ('standalone-sqlite', 'tests/home_states/test_delivery_semantics_sqlite.py', []),
    ('legacy-result-artifacts', 'tests/home_evolution/test_home_result_artifact_grouping.py', []),
    ('legacy-home-queries', 'tests/home_evolution/test_home_queries.py', []),
    ('canonical-verification', 'tests/test_verification.py', ['-k', 'test_ts4_complete_with_criteria_parks_in_verifying or test_ts5_verify_pass_completes_with_verified_by_on_the_canonical_event or test_ts6_verify_fail_drives_rework_cycles_with_renewed_lease'])]
lines[node.lineno - 1:node.end_lineno] = ['cases = ' + repr(cases) + '\n']
source = ''.join(lines).replace("HERE / 'final-allocation.json'", "HERE / 'metadata-final-allocation.json'")
(HERE / 'run_metadata_final.py').write_text(source, encoding='utf-8')
print('Prepared metadata-only final contract and focused regressions.')
