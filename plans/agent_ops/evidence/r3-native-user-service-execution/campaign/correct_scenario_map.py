"""Editorial scenario-map correction only; no campaign action or observation."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import shutil

root = Path(__file__).resolve().parent
public = root / 'public-campaign'
repo = Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
ledger_path = repo / 'plans/agent_ops/ledger.json'
ledger = json.loads(ledger_path.read_text(encoding='utf-8'))
fixed_path = repo / ledger['plan']


def digest(path):
    data = path.read_bytes()
    return {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}


assert digest(fixed_path)['sha256'] == ledger['plan_sha256']
fixed = fixed_path.read_text(encoding='utf-8')
manifest_path = public / 'artifact-manifest.json'
manifest_before = digest(manifest_path)
manifest = json.loads(manifest_path.read_text())
assert all(digest(public / name) == facts for name, facts in manifest['files'].items())
qualification_path = public / 'qualification.json'
qualification_before = digest(qualification_path)
qualification = json.loads(qualification_path.read_text())
before_map = qualification['supports']
immutable_fields = {k: v for k, v in qualification.items() if k != 'supports'}
scopes = {
    'SVC-T07': (
        'Installed user tasks start the selected empty runtimes; canonical readiness confirms instance, version and Task Scheduler supervisor. Repeated start retains the same PID, birth and generation.',
        'Windows empty-runtime scope; no broader platform or provider qualification.'),
    'SVC-T14': (
        'PARTIAL: inspected saved absolute executable, selected cwd/project, configuration arguments and approved PATH/environment subset; PATH normalization follows the installed Path.resolve contract. The actual registered tasks reached canonical readiness using that saved context.',
        'The campaign did not deliberately vary CLI cwd/PATH between install and start or independently sample the running child cwd/PATH. No provider, vault or effective provider configuration was exercised.'),
    'SVC-T17': (
        'PARTIAL: repeated install preserved the same owned task definition digest; repeated start also preserved the same process identity. Disable/enable each ran once per component.',
        'Repeated enable and preservation of an externally modified task definition were not exercised in this native campaign.'),
    'SVC-T20': (
        'PARTIAL: explicit canonical stop drained each empty runtime and confirmed the exact owner exited. The following bounded observations remained stopped; no automatic restart was observed in those checkpoints.',
        'The next connect and its documented restart policy were not exercised. This does not establish unlimited-duration suppression from the finite stopped checkpoints.'),
    'SVC-T27': (
        'PARTIAL: owner/digest-fenced uninstall removed the two selected stopped tasks and retained their disposable homes.',
        'Execution in foreground after uninstall was not exercised; bytewise preservation of all data was not measured.')
}
new_map = []
for scenario_id, (observed, remaining) in scopes.items():
    literal = ledger['scenarios'][scenario_id]['requirement']
    assert f'| {scenario_id} | {literal} |' in fixed
    new_map.append({'id': scenario_id, 'literal_requirement': literal,
                    'scope': observed, 'remaining': remaining})
qualification['supports'] = new_map
assert {k: v for k, v in qualification.items() if k != 'supports'} == immutable_fields
qualification_path.write_text(json.dumps(qualification, indent=2) + '\n', encoding='utf-8')
manifest['files']['qualification.json'] = digest(qualification_path)
correction = {
    'kind': 'editorial_scenario_mapping_correction', 'at': datetime.now(timezone.utc).isoformat(),
    'reason': 'The prior map incorrectly associated enable/disable with SVC-T14 and used unrelated limitations for SVC-T17.',
    'authority': {'fixed_plan': ledger['plan'], 'fixed_plan_sha256': ledger['plan_sha256'],
                  'ledger_sha256': digest(ledger_path)['sha256']},
    'prior_manifest': manifest_before, 'prior_qualification': qualification_before,
    'before_supports': before_map, 'after_supports': new_map,
    'campaign_actions_or_observations_added': 0, 'unique_actions_remain': 24,
    'all_nonmapping_qualification_fields_unchanged': True,
    'actions_sha256_unchanged': digest(public / 'actions.json')['sha256'],
    'final_execution_record_sha256_unchanged': digest(public / 'attempt-3/execution-record.json')['sha256'],
    'no_ledger_status_promotion': True
}
(public / 'scenario-mapping-correction.json').write_text(json.dumps(correction, indent=2) + '\n', encoding='utf-8')
manifest['files']['scenario-mapping-correction.json'] = digest(public / 'scenario-mapping-correction.json')
shutil.copyfile(Path(__file__), public / 'correct_scenario_map.py')
manifest['files']['correct_scenario_map.py'] = digest(public / 'correct_scenario_map.py')
assert all(digest(public / name) == facts for name, facts in manifest['files'].items())
assert {p.relative_to(public).as_posix() for p in public.rglob('*') if p.is_file()} == set(manifest['files']) | {'artifact-manifest.json'}
manifest_path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'public': str(public), 'payloads': len(manifest['files']),
                  'manifest': digest(manifest_path), 'qualification': digest(qualification_path)}))
