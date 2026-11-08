"""Freeze reviewed preparation after exact package qualification. No execution."""
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).parent
D = ROOT / 'draft'
I = D / 'installation'
P = D / 'm1-codex-campaign-proposal-v9.json'
QUAL = Path('D:/Projetos/Techridy/okto_labs_okto_nexus/plans/agent_ops/evidence/r3-m1-check-recovery/qualification.json')
REFERENCE = Path('C:/Users/jpamb/AppData/Local/Temp/m1-check-recovery-inopit5p/venv/Lib/site-packages')

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')

assert sha(QUAL) == 'c524b04c21c9a9f0b2b3f0ff03ecf1410802bc368221732d322b8046fb0f36db'
assert json.loads((D / 'pure-tests-result.json').read_text())['status'] == 'PASS'
assert json.loads((I / 'direct-interpreter-final.json').read_text())['status'] == 'PASS'
assert not (ROOT / 'campaign').exists()
p = json.loads(P.read_text())
verified = 0
for entry in p['package_pins']['files']:
    target = Path(entry['path'])
    relative = target.relative_to(I / 'venv/Lib/site-packages')
    assert sha(REFERENCE / relative) == entry['sha256']
    assert not target.exists()
    verified += 1
assert verified == 982
for name,pin in p['package_pins']['packages'].items():
    pin['qualified_reference_package'] = str(REFERENCE / name)
    pin['qualification_status'] = 'QUALIFIED_ARTIFACT_NOT_INSTALLED_IN_TARGET'
    pin.pop('pending_reference_root', None)
p['package_pins']['qualified_reference_environment'] = str(REFERENCE.parent.parent)
p['package_pins']['status'] = 'QUALIFIED_ARTIFACTS_INSTALL_REQUIRED'
installer_path = I / 'timed_install.py'
text = installer_path.read_text()
assert 'FINAL_PINS_BOUND = False' in text
text = text.replace('FINAL_PINS_BOUND = False  # Root must bind qualified v9 pins and requalify before freeze.',
                    'FINAL_PINS_BOUND = True  # Exact v9 artifacts qualified; actual approval is still mandatory.')
installer_path.write_text(text, encoding='utf-8')
p['base06_installation'].update(
    status='PREPARED_QUALIFIED_REQUIRES_NEW_USER_APPROVAL',
    installer_enabled=True, script_sha256=sha(installer_path),
    direct_interpreter_qualification='PASS_OWN_BASE_PID_AND_VENV_PREFIX_PRODUCTS_ABSENT')
p['execution_bundle']['status'] = 'FROZEN_QUALIFIED'
p['execution_bundle']['qualification_scope'] = 'Finite pure preparation guards only; no v9 service/provider/runtime campaign. Exact product artifacts separately qualified in root environment; target product installation remains unexecuted and approval-gated.'
for entry in p['execution_bundle']['files'].values():
    assert Path(entry['path']).exists()
    entry['sha256'] = sha(entry['path'])
p['execution_bundle']['final_gate_result'] = str(D / 'final-gates-result.json')
p['controller_preparation'].update(
    status='QUALIFIED_PURE_V9_DELTA',
    v9_qualification={'result':str(D / 'pure-tests-result.json'),
                      'result_sha256':sha(D / 'pure-tests-result.json'),
                      'xml':str(D / 'pure-tests.xml'), 'xml_sha256':sha(D / 'pure-tests.xml'),
                      'controller_cases':24, 'installer_cases_in_initial_pass':27,
                      'limits':'Controller uses exact wheel ConnectionError class AST and pure Core event translation from pinned wheel, with fake transport; no product integration or campaign is claimed.'})
p['transport_reuse']['status'] = 'PREPARATION_QUALIFIED_NOT_EXECUTED'
p['transport_reuse']['controller'] = 'V9 policy/ancestry/receipt/state-format delta: 24 pure cases passed; historical v8 evidence remains separately identified.'
p['package_pin_status'] = {'current':'QUALIFIED_ARTIFACTS_INSTALL_REQUIRED',
    'required':'A new exact v9 approval is required for the one timed offline product installation; then verify the new target payload/import/pipcheck receipt before campaign effects.'}
p['status'] = 'PREPARED_FOR_REVIEW_NOT_AUTHORIZED'
p['blocking_preconditions_before_execution_request'] = [
    'Root completes final readonly composition/manifest review and exact named-task/port/fresh-root inspection before requesting approval.',
    'Obtain one explicit approval for this final v9 snapshot; old v7/v8 approvals and synthetic test receipts authorize no effect.'
]
p['completed_preparation_checks'] = {
    'qualified_nexus_artifact':{'wheel_sha256':p['package_pins']['packages']['okto_nexus']['sha256'],
        'commit':'44c3825445144fa48b5c5ccf6b0d2bd48b21c3b7', 'installed_unique_cases':59,
        'qualification':str(QUAL), 'qualification_sha256':sha(QUAL)},
    'qualified_reference_payloads_rechecked':982,
    'dependencies_only_target_files':3209,
    'direct_interpreter':'PASS own base PID equals child, correct disposable prefix, all products absent',
    'controller_pure_cases':24, 'installer_pure_cases_initial_pass':27,
    'entry_denials':12, 'final_touched_gates':str(D / 'final-gates-result.json'),
    'limits':'No preflight observation survives time indefinitely. Exact tasks/root/port and pins must be checked again after approval, immediately before effects.'
}
p['evidence_references']['scope'] = 'Unchanged component proofs retain their original limits; v9 controller and guards have separate finite pure preparation results. No v9 campaign is claimed.'
p['evidence_references']['nexus_check_recovery'] = p['completed_preparation_checks']['qualified_nexus_artifact']
# These are intentionally NOT an execution receipt or approval.
assert p['execution_authorized'] is False
assert p['authorization']['execution_authorized'] is False
assert p['controller_preparation']['approval_receipt_created'] is False
write(P,p)
source_map = json.loads((D / 'source-map.json').read_text())
for name,entry in source_map.items():
    entry['sha256'] = sha(D / name)
    assert sha(entry['source']) == entry['source_sha256']
    if entry['reuse']=='byte_identical': assert entry['sha256']==entry['source_sha256']
write(D / 'source-map.json',source_map)
write(D / 'reference-payload-proof.json',{
    'status':'PASS', 'reference_prefix':str(REFERENCE.parent.parent),
    'wheel_payloads_equal_reference_installed':982, 'target_products_present':False,
    'source_qualification_sha256':sha(QUAL), 'product_install_executed':False,
    'scope':'Read-only comparison against root-qualified reference. Target paths are prospective, not installed.'})
delta=json.loads((D/'delta-map.json').read_text())
delta['status']='PREPARATION_QUALIFIED_PENDING_FINAL_REVIEW_AND_APPROVAL'
delta['qualified_preparation']={'controller':24,'initial_installer':27,'entry_denials':12}
delta['must_qualify']=['Final touched installer/entry gates result required before publication; no campaign has run.']
delta['no_status_inheritance']='Only unchanged component proofs are reused; v9 pure results are separately recorded and do not qualify a live campaign.'
write(D/'delta-map.json',delta)
print(json.dumps({'proposal_sha256':sha(P),'installer_sha256':sha(installer_path),
                  'qualified_reference_payloads':verified,'execution_authorized':False}))
