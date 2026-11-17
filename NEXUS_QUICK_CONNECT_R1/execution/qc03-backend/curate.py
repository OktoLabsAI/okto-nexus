"""Curate bounded backend qualification; no application startup or external calls."""
from datetime import datetime, timezone
import hashlib
import ast
import importlib.util
import json
from pathlib import Path
import platform
import sys
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'src'))
import okto_nexus  # noqa: E402
FILES = [
    'src/okto_nexus/domain/connection_public_ids.py',
    'src/okto_nexus/migrations/168_connection_public_ids.sql',
    'src/okto_nexus/application/connection_project_context.py',
    'src/okto_nexus/application/connection_public_ids.py',
    'src/okto_nexus/application/connection_workspaces.py',
    'src/okto_nexus/application/workspace_paths.py',
    'src/okto_nexus/application/connection_setup.py',
    'src/okto_nexus/application/connection_test.py',
    'src/okto_nexus/domain/home_entries.py',
    'src/okto_nexus/adapters/outbound/sqlite/home_entries.py',
    'src/okto_nexus/adapters/outbound/sqlite/connection_catalog.py',
    'src/okto_nexus/adapters/inbound/http/runtime_v1.py',
    'src/okto_nexus/adapters/inbound/http/connection_public_ids.py',
    'src/okto_nexus/adapters/inbound/http/dashboard_runtime.py',
    'tests/execution_r4/test_public_connection_ids.py',
    'tests/execution_r4/test_connection_workspaces.py',
]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def junit(name):
    path = OUT / name
    suites = ET.parse(path).getroot().findall('testsuite')
    return dict(file=name, sha256=sha(path), tests=sum(int(s.attrib['tests']) for s in suites),
                failures=sum(int(s.attrib['failures']) for s in suites),
                errors=sum(int(s.attrib['errors']) for s in suites),
                time_seconds=sum(float(s.attrib['time']) for s in suites),
                nodes=[c.attrib.get('classname', '') + '::' + c.attrib['name']
                       for suite in suites for c in suite.findall('testcase')])


pins = {name: sha(ROOT / name) for name in FILES}
(OUT / 'source-pins.json').write_text(json.dumps(pins, indent=2) + '\n', encoding='utf-8')
cuts = [junit(name) for name in ('setup-registry-junit.xml', 'final-focal-junit.xml',
                               'final-focal-v2-junit.xml', 'receipt-first-junit.xml')]
assert [(c['tests'], c['failures'], c['errors']) for c in cuts] == [(41, 0, 0), (24, 2, 0), (30, 0, 0), (2, 0, 0)]
vendor = {
    'vendor/wheels/okto_nexus_connector_core-0.0.14-py3-none-any.whl':
        'ea1797805279667a5b39fdb6e9e6185ed8dcb958a1c7f98e91651e841754dca5',
    'vendor/ci/okto_nexus_connector-0.0.13-py3-none-any.whl':
        '4095484f14110b845b3481941330810f3de1d8fadf9051de0b724cb824177b90',
}
assert all(sha(ROOT / name) == expected for name, expected in vendor.items())
report = dict(
    version=1, created_at=datetime.now(timezone.utc).isoformat(), status='PASS_SCOPED_BACKEND',
    environment=dict(python=sys.version, executable=sys.executable, platform=platform.platform(),
        checkout_source_first=True, installed_qualification=False,
        nexus_origin=okto_nexus.__file__,
        core_origin=importlib.util.find_spec('nexus_connector_core').origin,
        pytest_origin=importlib.util.find_spec('pytest').origin),
    source_pins_file='source-pins.json', source_pins_sha256=sha(OUT / 'source-pins.json'),
    vendor_pins=vendor, cuts=cuts,
    interpretation=[
        '41 antecedent PASS: 17 new namespace cases plus 24 existing Setup cases; before the exact JSON index hint.',
        '24 intermediate: 22 PASS, two FAIL: strict old workspace envelope oracle and index-choice guard. Both retained.',
        '30 PASS: corrected additive envelope oracle, exact indexed projection, new malformed/remote/code negatives, golden legacy hash, catalog and Home/detail regressions.',
        'After the 30-case module was loaded, one receipt-first guard was added to Reserve. Final two focal PASS cover that exact delta and bound replay. No aggregate single-run claim.',
    ],
    contracts=dict(
        setup_optional='public_connection {version:1,connect_id,reservation_ref,project_revision}; absent/null omitted before hashing',
        finish='result.public_connection {version:1,connect_id,reservation_ref,revision:int,state:bound,canonical_ref:full7tuple}',
        namespace='server_id + workspace_id + lowercase ASCII connect_id; reserved/bound/retired remain occupied',
        new_project='Server-private durable draft, no workspace/agent creation at Reserve; one pending exact-directory draft',
        atomicity='Finish validates reservation/project before writes; public binding, workspace, grants, and receipt share the existing outer UoW',
        idempotence='same reservation + actor audit identity + setup intent + normalized full request hash; committed receipt checked before new reservation',
        adoption='operator-approved exact full binding reference and binding revision; metadata only; canonical revision materialization may occur',
        cursor='unsigned opaque scope/principal/Server/revision/limit fence; no token/cookie/path inside cursor',
        public_errors=['HARNESS_ID_ALREADY_EXISTS', 'CONNECT_ID_PENDING'],
        project_proof='read-only authorized Server embedded directory identity + current approved mapping revisions; remote logical proof never reads local mappings or stats paths',
        malformed_mapping='PROJECT_INVENTORY_INCOMPLETE; never a false absence or new project',
        legacy_hash=None,
    ),
    read_bounds=dict(public_ids='ordered SQL aggregate and LIMIT page in one read UoW',
        workspaces='ordered SQL aggregate and keyset LIMIT page in one read UoW; legacy after_workspace_id preserved',
        project_mappings='LIMIT 10001; over 10000 fails incomplete; no filesystem scan of stored roots',
        workspace_paths='LIMIT 10001; over 10000 fails incomplete',
        home_projection='no new query; exact seven-reference + adapter LEFT JOIN using unique server/executor/binding JSON index; EXPLAIN guarded'),
    limits=[
        'Operator maintenance is the existing global authority. Namespace is shared per Server/project, not a new per-human ownership partition. Saga actor audit identity follows existing setup_actor; cursor human fence remains separate.',
        'No automatic release, expiry, replacement, ID reassignment, or inference that a pending/unknown outcome is empty.',
        'Reserved is neither a binding nor readiness, native success, a grant, or permission to execute.',
        'Existing API without public_connection remains supported; legacy rows receive no implicit ID or rewrite.',
        'Fixtures use real SQLite and in-process HTTP with inert candidate metadata and explicit verified-Test injection; no browser/native/provider qualification.',
        'No current-installed package, CI matrix, LiveMCP, throughput, percentile, or SLO claim in this cut.',
        'No personal prefix reinstall, authentication/config reading, credential copy, model invocation, or provider access.',
    ],
    cleanup=dict(pytest_sessions_terminal=True, owned_native_or_service_subprocesses_started=0,
                 model_calls=0, provider_calls=0, git_mutations=0, ledger_edits=0),
    ruff=dict(result='PASS', toolref='2cfab1', scope='new modules plus modified workspace reader/tests'),
)
# Preserve the literal golden from the passing fixed oracle without transcription.
tree = ast.parse((ROOT / 'tests/execution_r4/test_public_connection_ids.py').read_text(encoding='utf-8'))
golden = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
              and node.name == 'test_legacy_request_hash_matches_frozen_installed_pr27')
report['contracts']['legacy_hash'] = next(node.value.value for node in golden.body
    if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'expected'
                                          for target in node.targets))
(OUT / 'qualification.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
print(json.dumps(dict(report=str(OUT / 'qualification.json'), sha256=sha(OUT / 'qualification.json'),
                      source_pins=len(pins), cuts=[(c['tests'], c['failures']) for c in cuts])))
