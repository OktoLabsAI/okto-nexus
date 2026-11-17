from pathlib import Path
import hashlib
import json
import shutil
import sqlite3

here = Path(__file__).resolve().parent
root = here.parents[3]
control = Path('C:/Users/jpamb/AppData/Local/Temp/nexus-ui043-third-human-control-v1h34gtf')
dest = here / 'third-run'
dest.mkdir(exist_ok=True)
for name in ('ready.json', 'cleanup.json', 'actions.json', 'peer-status.json'):
    shutil.copy2(control / name, dest / name)
for name in ('fixture.py', 'observation_window.py'):
    shutil.copy2(here / name, dest / (name + '.antecedent'))
ready = json.loads((dest / 'ready.json').read_text())
actions = json.loads((dest / 'actions.json').read_text())
clicks = [a for a in actions if a['type'] == 'ui_action']
writes = [a for a in actions if a['type'] == 'http' and a['method'] != 'GET']
db = Path(ready['home']) / 'home/nexus.db'
conn = sqlite3.connect(db.as_uri() + '?mode=ro', uri=True)
conn.row_factory = sqlite3.Row
facts = {
    'setup_commits': conn.execute('SELECT count(*) FROM connection_setup_commits').fetchone()[0],
    'bindings': [dict(r) for r in conn.execute('SELECT binding_id,binding_revision FROM execution_bindings')],
    'sessions': conn.execute('SELECT count(*) FROM execution_sessions').fetchone()[0],
    'original_grants_preserved': all(dict(conn.execute('SELECT grant_id,expires_at,max_executions FROM runtime_execution_grants WHERE grant_id=?', (g['grant_id'],)).fetchone()) == g for g in ready['original_grants']),
}
conn.close()
assert len(clicks) >= 22
assert len(writes) == 2 and all(w['status'] == 200 for w in writes)
assert facts['setup_commits'] == 1 and len(facts['bindings']) == 3 and facts['original_grants_preserved']
feedback = 'Consegui, mas ainda acho que tem muito ruído desnecessário com informacoes colapsáveis que nao entendi e nao vi valia. O botão Open Context me causou dúvida no entendimento. No final, fiquei na duvida se a conexao tinha ocorrido tambem. Acho que se nesse momento algo mais gráfico, um loader com icone de sucesso/erro pode ser aplicado pra facilitar o entendimento. No lugar do botao Open Context podemos ter algo mais util para o contexto.'
result = {
    'status': 'NOT_COMPLETE_CLARITY_INSUFFICIENT_NO_PASS',
    'participant': 'Same participant, already exposed and given feedback in two previous journeys; iterative third journey, not a new blind novice study.',
    'anonymous_feedback_literal': feedback,
    'feedback_source': 'Parent /root final feedback message; exact chat send/response times not available.',
    'observations': {'reported_functional_cut_click_count': 22, 'reported_cut_read_at': '2026-11-17T01:35:45.158934+00:00', 'final_raw_click_count': len(clicks), 'later_exploration_clicks': clicks[22:], 'first_click_at': clicks[0]['at'], 'last_click_at': clicks[-1]['at'], 'writes': writes,
        'original_connection_read': [a for a in actions if a.get('path') == '/api/v1/runtime-management/connections/bindings/binding'],
        'post_finish_target_reads': [a for a in actions if a.get('path') == '/api/v1/home/target' and a['at'] >= '2026-11-17T01:31:30']},
    'technical_result': 'Original connection opened via canonical GET200; simulated Test and canonical Finish both200; one setup commit and three retained bindings. Technical success does not establish clear completion for the participant.',
    'facts': facts,
    'context': {'project': 'Sample project', 'workspace_id': 'ws', 'authorized_owned_local_folder': str(Path(ready['home']) / 'participant-project'),
        'folder_precondition': 'Existing two connections were remote; no local Server-folder mapping was fabricated. Root was supplied the real owned local project folder as neutral fixture data before Add. Delivery to participant is not independently logged here.'},
    'limits': ['No completion duration or exact task-send/feedback time inferred from click timestamps. Functional cut had22 clicks; final raw log has25 additional exploration clicks, not automatically attributed to task completion.',
        'HTTP log intentionally records path/status, not query strings, response bodies or typed input. Post-Finish target reads200 are proven, but their binding/group identities are not retained.',
        'No provider or native binary invocation; ConnectionTests peer is simulated. This is a usability journey, not real harness qualification.',
        'Read observation window60min is independent of original lane10min and native request120s. No authority renewal, extension request or facilitator HITL trigger used.',
        'Participant reported success but continuing noise and uncertainty about connection completion; no usability scenario promoted to PASS.'],
    'cleanup': {'browser_session': 'ui043-third-human', 'browser_close_exit_code': 0, 'fixture_exec_session': 99505, 'fixture_exit_code': 0,
        'physical_check_at_utc': '2026-11-17T01:43:58.0185709Z', 'browser_pid43120_present': False, 'fixture_pid57448_present': False, 'listener57276_present': False,
        'peer_wss_factory_closed': json.loads((dest / 'cleanup.json').read_text()), 'data_preserved': True},
    'product_source_at_curation_sha256': {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in (
        'frontend/src/components/onboarding/ProjectConnectFlow.tsx', 'frontend/src/components/ConnectionWorkflow.tsx',
        'src/okto_nexus/adapters/inbound/http/static/assets/index-CKlKNFgD.js', 'src/okto_nexus/adapters/inbound/http/static/assets/index-BP1to-F2.css')},
}
(dest / 'qualification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
pins = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in dest.iterdir() if p.is_file() and p.name != 'manifest.json'}
(dest / 'manifest.json').write_text(json.dumps(pins, indent=2), encoding='utf-8')
state_path = here / 'runtime-state.json'
state = json.loads(state_path.read_text())
state['status'] = result['status']
state['human_qualification'] = 'third-run/qualification.json'
state['cleanup'] = result['cleanup']
state_path.write_text(json.dumps(state, indent=2), encoding='utf-8')
old_manifest = json.loads((here / 'pr14-manifest-copy.json').read_text())
old = here.parent / 'pr14-human-session'
mismatches = [name for name, digest in old_manifest.items() if hashlib.sha256((old / name).read_bytes()).hexdigest() != digest]
assert not mismatches, mismatches
outer = {str(p.relative_to(here)).replace('\\', '/'): hashlib.sha256(p.read_bytes()).hexdigest() for p in here.rglob('*') if p.is_file() and p != here / 'manifest.json' and '__pycache__' not in p.parts}
(here / 'manifest.json').write_text(json.dumps(outer, indent=2), encoding='utf-8')
print(json.dumps({'qualification_sha256': pins['qualification.json'], 'third_run_entries': len(pins), 'outer_entries': len(outer), 'prior_pr14_mismatches': mismatches, 'facts': facts}, ensure_ascii=False))
