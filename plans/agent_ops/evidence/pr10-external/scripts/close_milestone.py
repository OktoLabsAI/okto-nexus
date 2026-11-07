"""Close only the qualified OBS11 scope, preserving fixed-plan outstanding work."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
OUT = REPO / 'plans/agent_ops/evidence/pr10-external'
sha = lambda data: hashlib.sha256(data).hexdigest()
reports_path = OUT / 'reports.json'
reports = json.loads(reports_path.read_text(encoding='utf-8'))
assert reports['collection_phase'] == 'closed_qualified_milestone'
assert not (OUT / 'artifact-manifest.json').exists()
count = reports['overlap_policy']['installed_final_candidate_cases']
union = reports['overlap_policy']['installed_distinct_cases_all_candidates']
assert count > 200 and union >= count

for name in ('wheel-build.log', 'close_milestone.py', 'verify_artifacts.py'):
    source = ROOT / name
    target = OUT / ('diagnostics/' if name.endswith('.log') else 'scripts/') / name
    data = source.read_bytes()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        assert target.read_bytes() == data
    else:
        target.write_bytes(data)
    path = target.relative_to(REPO).as_posix()
    if not any(row['path'] == path for row in reports['retained_inputs']):
        reports['retained_inputs'].append(dict(path=path, original_path=str(source), bytes=len(data),
            sha256=sha(data), original_sha256=sha(data), exact_original_bytes=True))

initial_build = next(row for row in reports['diagnostics'] if row['kind'] == 'initial_build_failure')
assert sha((OUT / 'diagnostics/wheel-build.log').read_bytes()) == initial_build['source_log_sha256']
initial_build.update(log_copied=True, retained_log='plans/agent_ops/evidence/pr10-external/diagnostics/wheel-build.log')
reports['final_artifact_manifest'] = 'plans/agent_ops/evidence/pr10-external/artifact-manifest.json'
reports['artifact_policy']['scope'] = ('Closed source/frontend/installed reports, exact package proofs, '
    'build/qualification drivers, safe browser artifacts and exact trace resources, all benchmark candidates '
    'and retired tests. The manifest binds the entire evidence directory. No database, private bearer file or wheel is collected.')
for row in reports['retained_inputs']:
    assert sha((REPO / row['path']).read_bytes()) == row['sha256'], row['path']
reports_path.write_text(json.dumps(reports, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')

report = REPO / 'plans/agent_ops/evidence/pr10-external.md'
content = report.read_text(encoding='utf-8')
content = content.replace("historical evidence. This candidate's qualification is still in progress.",
                          'historical evidence. The final installed regression is described below.')
content = content.replace('All 672 package files again match source and installed bytes. Its broader\n'
    'installed attention regression is currently running. The source reports cover\n'
    '340 distinct cases still present in the current tree; nine retired memo cases\n'
    'are historical only and are not added to that number.',
    f'All 672 package files again match source and installed bytes. Its broader\n'
    f'installed attention regression qualified {count} case identities: 291 passed in\n'
    f'the broad run and the corrected migration case passed in a focused rerun.\n'
    f'Across V1, V2 and V4, installed reports cover {union} distinct case identities;\n'
    f'reruns are not added together. The source reports cover 341 distinct cases\n'
    f'still present in the current tree. Nine retired memo cases are historical\n'
    f'only and are not added to that number. The current UI has 121 passing cases.\n\n'
    'The exact retained bytes are enumerated in\n'
    '[`pr10-external/artifact-manifest.json`](pr10-external/artifact-manifest.json),\n'
    'including the original failed build log and earlier candidate measurements.\n'
    'The manifest verifier also checks the Git index bytes before commit.')
content += ('\nThe broad V4 campaign retained one `FileNotFoundError` in an old migration\n'
    'test that assumed a source checkout. The corrected test reads SQL through\n'
    '`importlib.resources` and expects the current migrations through 165, while\n'
    'preserving its backfill, privacy and immutable-history assertions. It passed\n'
    'separately on source and the unchanged installed wheel. The original XML,\n'
    'qualification proof and test bytes remain under `final/initial`; the focused\n'
    'installed correction is under `final/followup`. No all-green broad rerun or\n'
    'synthetic merged XML is claimed.\n')
assert 'currently running' not in content and 'still in progress.' not in content
report.write_text(content, encoding='utf-8')

path = REPO / 'plans/agent_ops/ledger.json'
ledger = json.loads(path.read_text(encoding='utf-8'))
assert ledger['tasks']['OBS-11']['status'] == 'IN_PROGRESS'
assert ledger['tasks']['OBS-12']['status'] == 'IN_PROGRESS'
assert ledger['milestones']['PR-10']['status'] == 'IN_PROGRESS'
assert ledger['plan_sha256'] == '20d0fafdedc793b97a277f5d41355d7d597ff724a77687394215eea3113ba996'
task = ledger['tasks']['OBS-11']
task['status'] = 'VERIFIED'
task['result'] = (f'Three external watch kinds, exact inspection and complete agent summaries are qualified. '
    f'Current source coverage has 341 distinct cases; frontend has 121 passes. Final non-editable V4 package '
    f'qualified {count} installed cases (291 broad passes plus one corrected migration rerun); {union} distinct installed cases across candidates are not additive to source. '
    'Real Chrome/HTTP/SQLite with synthetic peers and final 4096-instance measurement passed. '
    'OBS12 wiring, joint R3 and real provider/client/native-service acceptance remain open.')
task['limitations'] = [item for item in task['limitations'] if item != 'V4 package functional regression is still running.']
task['subscopes']['v4_installed_regression'] = 'VERIFIED'
evidence = ['plans/agent_ops/evidence/pr10-external.md',
    'plans/agent_ops/evidence/pr10-external/reports.json',
    'plans/agent_ops/evidence/pr10-external/final/initial/installed.xml',
    'plans/agent_ops/evidence/pr10-external/final/followup/installed.xml',
    'plans/agent_ops/evidence/pr10-external/artifact-manifest.json']
for item in evidence:
    for rows in (task['tests'], ledger['milestones']['PR-10']['evidence']):
        if item not in rows:
            rows.append(item)
for identity in ('OB-09', 'OB-15', 'OB-16', 'OB-21', 'OB-24'):
    row = ledger['scenarios'][identity]
    for item in evidence[:3]:
        if item not in row['evidence']:
            row['evidence'].append(item)
ledger['scenarios']['OB-09'].setdefault('subscopes', {})['browser_expiry_and_activity_summary'] = 'VERIFIED'
for identity in ('OB-15', 'OB-16'):
    ledger['scenarios'][identity].setdefault('subscopes', {})['installed_canonical_queue_isolation'] = 'VERIFIED'
ledger['scenarios']['OB-21'].update(status='VERIFIED',
    result='Closed payloads and escaped plain-text browser rendering reject active HTML/URLs; no generated command or prompt action. Real browser trace contains no credential headers; private bearer files are excluded.')
ledger['scenarios']['OB-21']['subscopes']['real_browser_untrusted_text_and_trace_audit'] = 'VERIFIED'
ledger['scenarios']['OB-24']['subscopes']['installed_core_synthetic_factory_and_browser_off'] = 'VERIFIED'
assert ledger['scenarios']['OB-19']['status'] == 'NOT_RUN'
assert ledger['scenarios']['OB-24']['status'] == 'IN_PROGRESS'
ledger['updated_at'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
ledger['history'].append(dict(date='2026-11-07', milestone='PR-10', status='IN_PROGRESS',
    summary=f'OBS11 qualified: final V4 installed {count} passes, 341 current source cases, 121 frontend passes, '
        'real browser and 24/24 volume samples. OBS12 and full R3 remain open; no real-provider/client/service acceptance inferred.',
    evidence=evidence))
path.write_text(json.dumps(ledger, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
markdown = REPO / 'LEDGER_CODEX_NEXUS_INTEGRACAO_ATENCAO_ONBOARDING.md'
with markdown.open('a', encoding='utf-8') as handle:
    handle.write('\n## 2026-11-07 — PR-10a: OBS-11 qualificado\n\n'
        f'A wheel V4 qualificou {count} casos: 291 passaram na regressão ampliada e um teste antigo de migração, que dependia do checkout, passou após correção em execução focal. O relatório original com a falha permanece retido. '
        f'Os relatórios instalados dos candidatos somam {union} identidades distintas, sem somar reexecuções. '
        'Os 341 casos fonte atuais, 121 casos frontend, browser real com dados sintéticos e 24/24 amostras de volume '
        'sustentam OBS-11 como VERIFIED. As evidências preservam as falhas iniciais, candidatos substituídos e limites da campanha. '
        'Manifesto e verificador vinculam os bytes retidos aos arquivos staged antes do commit.\n\n'
        'OBS-12, PR-10 completo, campanhas reais e regressão conjunta R3 continuam pendentes. '
        'OB-19 permanece NOT_RUN e OB-24 IN_PROGRESS. Não houve qualificação nova de provider, cliente MCP real ou serviço nativo. '
        'Detalhes: [PR-10](plans/agent_ops/evidence/pr10-external.md).\n')
print(json.dumps(dict(installed_final=count, installed_union=union, obs11='VERIFIED', pr10='IN_PROGRESS')))
