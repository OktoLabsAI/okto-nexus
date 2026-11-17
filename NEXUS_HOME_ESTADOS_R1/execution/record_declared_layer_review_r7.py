"""Use each scenario's declared levels rather than inventing extra gates."""
from datetime import UTC, datetime
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
path = HERE.parent / 'NEXUS_HOME_ESTADOS_LEDGER_R1.json'
ledger = json.loads(path.read_text(encoding='utf-8'))
review = json.loads((HERE / 'remaining-qualification-r7-next/backend-review.json').read_text(encoding='utf-8'))
for identifier in ('HST-T-E08', 'HST-T-E09'):
    row = next(item for item in review['scenarios'] if item['id'] == identifier)
    test = next(item for item in ledger['tests'] if item['id'] == identifier)
    assert row['all_given_when_then_covered']
    assert row['review_assessment'] == 'COVERED_AT_DECLARED_LAYERS_PROPOSE_PASS'
    assert test['level'] == row['level'] == 'unidade + SQLite/HTTP + apresentação'
    entry = dict(commit='01b0de385398950ac4547aa8a5dcbc29473c12cb + exact supplementary test511ce2cf',
        timestamp=datetime.now(UTC).isoformat(),
        artifact_path='execution/remaining-qualification-r7-next/backend-review.json',
        environment='Frozen installed R7 supplementary HTTP/SQLite and current Node presentation; separate prior canonical inert-protocol browser terminal checks',
        command_or_procedure='Review literal Given/When/Then against the already executed assertions at the required unit+SQLite/HTTP+presentation levels',
        result='PASS at declared layers: unsuccessful outcome, partial capture/evidence access and explicit presentation without generic replay',
        limitations='Historical migrated capture fixtures are not real native execution. Partial-output DOM was not asserted and is not claimed; browser is not a separate mandatory level in this scenario. Native terminal/presentation predecessor is identified separately. No extra test or producer capability is inferred.')
    test['status'] = 'PASS'
    if not any(old.get('artifact_path') == entry['artifact_path'] for old in test['evidence']):
        test['evidence'].append(entry)
    test['execution_notes'] = entry['limitations']
ledger['execution']['declared_layer_reconciliation_r7'] = dict(
    report='execution/remaining-qualification-r7-next/backend-review.json',
    actual_existing_evidence_promotions=['HST-T-E08', 'HST-T-E09'],
    normative_levels_changed=False, new_execution=False,
    reason='Earlier notes incorrectly required a new browser/native proof beyond these two literal scenario levels.')
path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(ledger['execution']['declared_layer_reconciliation_r7']))
