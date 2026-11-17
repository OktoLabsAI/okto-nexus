"""Retain the real R7 name defect; R8 source fix is not browser verification."""
from datetime import UTC, datetime
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
path = HERE.parent / 'NEXUS_HOME_ESTADOS_LEDGER_R1.json'
ledger = json.loads(path.read_text(encoding='utf-8'))
negative_path = 'remaining-qualification-r7-next/experience-batch/naming-r7/qualification.json'
negative = json.loads((HERE / negative_path).read_text())
assert negative['status'] == 'FAIL_PRODUCT_ACCESSIBLE_NAME'
assert negative['runtime']['checks'][0]['actual']['ariaSnapshot'] == '- button'
assert negative['cleanup']['exit_code'] == 0 and not negative['physical']['active_resources']
frontend = json.loads((HERE / 'frontend-r8-menu/qualification.json').read_text())
assert frontend['status'] == 'PASS' and frontend['input_drift'] == []
entry = dict(commit='01b0de385398950ac4547aa8a5dcbc29473c12cb', timestamp=datetime.now(UTC).isoformat(),
    artifact_path='execution/' + negative_path,
    environment='Frozen R7 wheel; actual own Chrome AX; two registered connections, zero runtime sessions/operations/provider calls',
    command_or_procedure='Read header-menu actual ariaSnapshot and label/title/text; preserve real failing predicate before source edit',
    result='FAIL real I01 accessible name: AX button unnamed, aria-label/title null and text empty; normal0/physical0/payload1031drift0',
    limitations='This is a product naming defect, not an oracle failure. No complete keyboard or screen-reader qualification.')
for test in ledger['tests']:
    if test['id'] == 'HST-T-I01':
        test['status'] = 'FAIL'
        if not any(old.get('artifact_path') == entry['artifact_path'] for old in test['evidence']):
            test['evidence'].append(entry)
        test['execution_notes'] = 'R8 source adds Application menu and expanded state; Node404/TSC/Vite pass. New installed package/browser verification pending; full keyboard criterion not inferred.'
for task in ledger['tasks']:
    if task['id'] in ('HST-026', 'HST-028', 'HST-031', 'HST-032'):
        if not any(old.get('artifact_path') == entry['artifact_path'] for old in task['evidence']):
            task['evidence'].append(entry)
ledger['execution']['r8_menu_accessibility'] = dict(
    cause='Header menu was an icon-only button with no accessible name.',
    reproduction=entry['artifact_path'], source_fix='Application menu aria-label and actual expanded state',
    frontend='execution/frontend-r8-menu/qualification.json', node='PASS404', typescript_vite='PASS',
    original_checkout=True, input_drift=[],
    bundle='assets/index-Cyg0aKfe.js', css='assets/index-Bh2ghaTD.css',
    installed='PENDING_NEW_R8_PREFIX', browser='PENDING_NAMING_THEN_EXPERIENCE',
    backend_source_changed=False, human='NOT_INVITED')
ledger['execution']['local_usability_candidate']['state'] = 'ADDITIONAL_FUNCTIONAL_QUALIFICATION_IN_PROGRESS; menu fix awaits installed proof'
ledger['execution']['local_usability_candidate']['pending_local_scopes'] = [
    'R8 installed menu-name/keyboard proof', 'backend first functional batch',
    'security/observation/CLI/legacy compatibility increments', 'experience/scoped stream follow-ups']
path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(ledger['execution']['r8_menu_accessibility']))
