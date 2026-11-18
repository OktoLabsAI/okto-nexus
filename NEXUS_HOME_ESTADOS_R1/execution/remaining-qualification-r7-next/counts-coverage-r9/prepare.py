"""Static pin preparation only; never import product or allocate test roots."""
import ast
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
BACKEND = HERE.parent / 'backend-batch'
COMPAT = HERE.parent / 'compat-batch'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


for name in ('run.py', 'test_counts_coverage.py', 'prepare.py'):
    ast.parse((HERE / name).read_text(encoding='utf-8'))
prior = json.loads((COMPAT / 'PREPARED-S3-R9-v2.json').read_text(encoding='utf-8'))
ready = REPO / 'NEXUS_HOME_ESTADOS_R1/execution/package-hst-r9/READY.json'
runtime = json.loads(ready.read_text(encoding='utf-8'))
command = ready.parent / 'owned_commands.py'
environment = Path(prior['environment_helper'])
copies = {str(HERE / 'test_counts_coverage.py'): 'tests/execution_r4/test_counts_coverage_r9.py',
    str(BACKEND / 'canonical_owner_v5.py'): 'tests/execution_r4/backend_batch_owner.py',
    str(BACKEND / 'protocol_fixture.py'): 'tests/execution_r4/backend_batch_protocol.py',
    str(BACKEND / 'peer_source.py'): 'tests/execution_r4/backend_batch_peer_source.py'}
helpers = [HERE / name for name in ('run.py', 'test_counts_coverage.py', 'prepare.py', 'plan.md')]
helpers += [Path(path) for path in copies] + [ready, command, environment]
manifest = {'status': 'PREPARED_NOT_EXECUTED', 'gate': 'ROOT_APPROVED_COUNTS_COVERAGE_R9',
    'source_commit': runtime['source_commit'], 'ready': str(ready), 'ready_sha256': sha(ready), 'wheel_sha256': runtime['wheel_sha256'],
    'source_pins': prior['source_pins'], 'payload_files': prior['runtime_payloads']['r9']['files'],
    'helper_sha256': {str(path): sha(path) for path in helpers}, 'copy_helpers': copies,
    'command_helper': str(command), 'environment_helper': str(environment),
    'expected_nodes': ['test_j01_exact_units_dedup_shared_work_and_page_independence', 'test_j02_actual_sqlite_operations_reader_failure_keeps_other_positives'],
    'preconditions_per_node': {'registered_harnesses': 2, 'human_actions': 3, 'canonical_deliveries': 2, 'sessions': 5,
        'live_authority_SQL_writes': False, 'shared_correlation': 'Historical read-fact only, same helper pattern previously qualified'},
    'limits': ['No timing metrics', 'Real installed HTTP/SQLite + actual Core to inert protocol peers, not real provider',
        'Historical coordination correlation is not a canonical handoff/claim execution proof',
        'J02 SQLite authorizer fault is test-scoped read failure, no DTO rewriting', 'Owner snapshot scope is six tables, not entire DB'],
    'static_checks': {'AST': 'PASS', 'Ruff_0_17_5': 'PASS', 'runtime_started': False},
    'node_deadline_seconds': 180}
assert len(manifest['source_pins']) == 1829 and len(manifest['payload_files']) == 1031
path = HERE / 'PREPARED.json'
assert not path.exists()
path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
print(json.dumps({name: sha(HERE / name) for name in ('run.py', 'test_counts_coverage.py', 'PREPARED.json')}, indent=2))
