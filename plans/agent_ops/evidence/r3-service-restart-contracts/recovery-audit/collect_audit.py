"""Read-only, finite SVC-T22/RG-05 evidence reconciliation; no test execution."""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
OUT = Path(__file__).resolve().parent
PLAN = 'PLANO_CODEX_NEXUS_INTEGRACAO_ATENCAO_ONBOARDING.md'
PLAN_HASH = '20d0fafdedc793b97a277f5d41355d7d597ff724a77687394215eea3113ba996'
RECOVERY = 'plans/agent_ops/evidence/r3-joint-contracts/recovery/reports.json'
CURRENT_XML = 'plans/agent_ops/evidence/r3-cooperative-drain/installed/nexus-installed-fixture-retry/canonical/tests.xml'
RECOVERY_XML = 'plans/agent_ops/evidence/r3-joint-contracts/recovery/ci/tests.xml'
NS14_XML = 'plans/r4_execution/evidence/ns14-01-nexus-installed.xml'
NS14_META = 'plans/r4_execution/evidence/ns14-01-nexus-installed.json'
AC05 = 'plans/agent_ops/evidence/r3-contract-closure/matrix.json'
QUAL = 'plans/agent_ops/evidence/r3-cooperative-drain/qualification.json'
LEDGER = 'plans/agent_ops/ledger.json'
RECON = Path('C:/Users/jpamb/AppData/Local/Temp/svc-t23-t24-reconciliation-ctw9ix9p/reconciliation.json')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(relative):
    return json.loads((ROOT / relative).read_text(encoding='utf-8'))


def passed(relative):
    return {c.get('classname') + '::' + c.get('name')
            for c in ET.parse(ROOT / relative).findall('.//testcase')
            if not any(c.find(tag) is not None for tag in ('failure', 'error', 'skipped'))}


assert sha(ROOT / PLAN) == PLAN_HASH
recovery = read(RECOVERY)
matrix = read(AC05)
ledger = read(LEDGER)
qualification = read(QUAL)
names = {name for item in recovery['test_map'] for name in item['cases']}
assert len(names) == recovery['unique_cases'] == 39
checks = []
for path in (RECOVERY_XML, CURRENT_XML):
    found = {identity.split('::', 1)[1] for identity in passed(path)}
    assert names <= found
    checks.append(dict(path=path, sha256=sha(ROOT/path), matched_unique_cases=39,
                       missing=[], note='Same identities; never add the two runs as 78 cases.'))

source_map = []
for item in recovery['test_map']:
    path, name = item['test'].split('::')
    text = (ROOT/path).read_text(encoding='utf-8')
    function = next(n for n in ast.walk(ast.parse(text))
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)
    source_map.append(dict(test=item['test'], line=function.lineno, end_line=function.end_lineno,
                           source_sha256=sha(ROOT/path), cases=item['cases'],
                           assert_count=sum(isinstance(n, ast.Assert) for n in ast.walk(function)),
                           retained_function_sha256=item['function_sha256']))

ac05_rows = [row for row in matrix['rows'] if row['criterion'] == 'AC-05']
ac05_checks = []
for row in ac05_rows:
    for evidence in row['evidence']:
        assert sha(ROOT/evidence['path']) == evidence['sha256']
        available = passed(evidence['path'])
        missing = sorted(set(evidence['passed_cases']) - available)
        assert not missing, (evidence['path'], missing)
        ac05_checks.append(dict(entry_path=row['entry_path'], path=evidence['path'],
                                sha256=evidence['sha256'], selected_passed_cases=evidence['passed_cases']))
assert 'test_ns14::test_ns14_01' in passed(NS14_XML)

ns14_text = (ROOT/'tests/execution_r4/test_ns14.py').read_text(encoding='utf-8')
old = subprocess.run(['rtk', 'proxy', 'git', 'show', '5a01c6ec:tests/execution_r4/test_ns14.py'],
                     cwd=ROOT, capture_output=True, check=True, encoding='utf-8').stdout
def function_ast(text):
    node = next(n for n in ast.parse(text).body if isinstance(n, ast.FunctionDef) and n.name == 'test_ns14_01')
    return ast.dump(node, include_attributes=False)
assert function_ast(ns14_text) == function_ast(old)
meta = read(NS14_META)
historical_wheels = {name: row['artifact']['sha256'] for name, row in meta['verified_packages'].items()}
head = subprocess.run(['rtk', 'proxy', 'git', 'rev-parse', 'HEAD'], cwd=ROOT,
                      capture_output=True, check=True, encoding='utf-8').stdout.strip()

groups = [
 ('Coordination creation/approval', 'tests/test_terminal_coordination.py',
  'One productive call/effect after lost reply/checkpoint; missing confirmed receipt stays uncertain. AC05 adds real subprocess death at DB/CLI commit boundaries.'),
 ('Participant exchange/handoff', 'tests/test_terminal_cooperation.py',
  'Fixed request IDs, exactly one effect; pre-send retry retains the same ID; missing prior receipt never recreates. AC05 adds real CLI death after exchange commit.'),
 ('Work and native decision', 'tests/execution_r4/test_terminal_work.py',
  'Lost resolve or submit reply recovers same operation, one open/send; lost approval/input reply produces one canonical decision and one native answer, or explicit refusal.'),
 ('Participant initialization and launch', 'tests/execution_r4/test_participant_init.py; tests/execution_r4/test_participant_launch.py',
  'Same setup intent, one backup/vault effect; file drift preserved; starting/started/exited checkpoint loss does not respawn. Launch process here is a double, not a living child.'),
 ('Local identity Finish', 'tests/execution_r4/test_terminal_identity.py',
  'One reviewed identity/key/grant/binding, one probe/turn; recovery returns original result with identical canonical snapshot.'),
 ('Remote bootstrap/approval/Finish', 'tests/execution_r4/test_remote_terminal_setup.py',
  'One bootstrap and one decision; missing secret material is not reissued; host Finish alone completes. Peer is explicit synthetic protocol double.'),
 ('Reviewed authorization renewal', 'tests/execution_r4/test_terminal_authorization.py',
  'AC05 complement: existing usable grant refuses duplicate issuance; lost issuance resolves same receipt even after later revocation. Not part of the selected 39.'),
]

rows = [dict(
    id='SVC-T22', literal=ledger['scenarios']['SVC-T22']['requirement'], plan_line=848,
    ledger_status_read=ledger['scenarios']['SVC-T22']['status'],
    proven=[
      'NS14-01 really kills the producing Server with os._exit and starts another PID on the same home after respecting the durable owner lease.',
      'The restarted Server returns the same SUBMITTED operation and UNKNOWN ownership/process state; control_available is false; the exact session claim/reservation remain; slot_released is false; no native runtime is constructed.',
      'Replay of the original request returns its original operation_id. A new intent is not admissible. Refusal reason is not independently a grant-expiry proof because the synthetic binary is removed.',
      'Current installed drain/restart contracts preserve uncertain owners, stores and pending release; they do not start another service generation when stop is pending. Native handles in those cases are doubles.'
    ],
    evidence=[NS14_XML, NS14_META, QUAL],
    evidence_limit='NS14 is retained historical installed evidence, not a current-wheel rerun. Its current test_ns14_01 AST equals historical commit 5a01c6ec and its process helper bytes equal the retained hash. The native backend is synthetic; no real child survival is established.',
    remaining='One concrete safe physical-child branch: an actual restart attempt while the current owner and its Core-owned Python child are alive must stay pending and retain claim/slot until proven release. The literal does not require the child to survive parent death.',
    minimum_next_case='New test_service_surviving_child.py, technical plan retained beside this matrix; no provider, personal service, scheduled task or weakened Job containment.',
    recommendation='PARTIAL: uncertain-operation restart branch evidenced; living-owned-child restart-pending branch awaits the targeted safe case.',
    product_defect_established=False),
 dict(
    id='RG-05', literal=ledger['scenarios']['RG-05']['requirement'], plan_line=972,
    ledger_status_read=ledger['scenarios']['RG-05']['status'],
    proven=[
      'All 39 named recovery identities pass in both the joint-contract run and the later cooperative-drain installed run; the latter uses Nexus cd1653/Core 1407014/Connector 73f1a3. These are 39 identities, not 78.',
      'The six selected flow groups plus the AC05 renewal complement assert original IDs, single effects or honest uncertainty without recreation. AC05 includes real process-death boundaries for coordination/cooperation.',
      'NS14 adds real Server restart with uncertain canonical work and retained ownership, at historical package scope.',
      'Current lifecycle guards refuse a new start while drain/exit remains unconfirmed; optional observation paths have no authority to replay productive work.'
    ],
    evidence=[RECOVERY, RECOVERY_XML, CURRENT_XML, AC05, NS14_XML, QUAL],
    path_map=[dict(path_group=g, source=s, assertion=a) for g,s,a in groups],
    remaining='No additional new-flow product defect or provider-only gap found. Finish the already-running current real Server-return qualification (T23/T24) and the one shared SVC-T22 living-child restart-pending case before a full current lifecycle-contract recommendation.',
    pending_scope='Coordinator reports T23/T24 use real old/new Server PIDs and a live Connector, but work and close finish before the crash. They compare unchanged operations/receipts and opens/sends=1. No PASS is inferred while execution is pending, and those cases do not substitute for uncertain work or a living child.',
    minimum_next_case='Reuse the SVC-T22 targeted safe case plus retain the final T23/T24 results when available; no separate provider/native-task campaign follows from this literal.',
    recommendation='CONTRACT_FLOW_MAP_SUPPORTED; final current lifecycle recommendation conditional on the two named safe qualifications. No status promotion performed.',
    product_defect_established=False)
]
inputs = {PLAN, LEDGER, RECOVERY, RECOVERY_XML, CURRENT_XML, NS14_XML, NS14_META, AC05, QUAL,
          'tests/execution_r4/test_ns14.py', 'tests/execution_r4/ns14_restart_process.py'}
inputs.update(item['test'].split('::')[0] for item in recovery['test_map'])
inputs.update(e['path'] for e in ac05_checks)
for p in ('tests/test_service_start.py', 'tests/test_service_drain_decision.py',
          'tests/execution_r4/test_service_cooperative_drain.py',
          'src/okto_nexus/application/service_lifecycle.py'):
    inputs.add(p)
document = dict(schema='r3-two-id-recovery-audit.v1', scope=['SVC-T22','RG-05'],
    nexus_head=head, plan=dict(path=PLAN, sha256=PLAN_HASH, unchanged=True),
    activity=dict(tests_executed=0, providers_started=0, services_started=0,
                  checkout_or_ledger_edits=0, status_promotions=0),
    rows=rows, selected_recovery_checks=checks, source_assertion_map=source_map,
    ac05_selected_pass_checks=ac05_checks,
    ns14_provenance=dict(historical_wheel_sha256=historical_wheels,
        current_function_ast_equals_commit='5a01c6ec',
        helper_sha256=sha(ROOT/'tests/execution_r4/ns14_restart_process.py')),
    current_installed_wheels={name:row['sha256'] for name,row in qualification['wheels'].items()},
    inputs={p:sha(ROOT/p) for p in sorted(inputs)},
    reconciliation_input=dict(path=str(RECON), sha256=sha(RECON)),
    limits=['No full provider recovery campaign claimed.', 'No foreign PID relabeled as an owned child.',
            'No real scheduled task/native service required by these two contract literals.',
            'No closed report was modified and no historical PASS was relabeled as current execution.'])
(OUT/'matrix.json').write_text(json.dumps(document, ensure_ascii=False, indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(matrix=str(OUT/'matrix.json'),sha256=sha(OUT/'matrix.json'),
                     selected_recovery_cases=39, ac05_checks=len(ac05_checks), tests_executed=0)))
