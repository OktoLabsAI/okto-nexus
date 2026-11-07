from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import shutil
import subprocess
import xml.etree.ElementTree as ET

root = Path(__file__).parent
repo = Path(r'D:/Projetos/Techridy/okto_labs_okto_nexus')
relative = 'plans/agent_ops/evidence/r3-service-boundaries'
dest = repo / relative
dest.mkdir(exist_ok=False)
baseline = Path(r'C:/Users/jpamb/AppData/Local/Temp/r3-svc-boundaries-installed-ktys6hfb/public')

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

for item in json.loads((baseline / 'artifact-manifest.json').read_text())['allowlist']:
    assert sha(baseline / item['path']) == item['sha256']
shutil.copytree(baseline, dest / 'before')
selected = ['package-proof.json', 'environment.json', 'pip-check.txt', 'distributions.json',
    'tests.txt', 'occupied-port.json', 'connect-interruption.json', 'startup-invalid_config.json',
    'startup-future_migration.json', 'startup-unavailable_storage.json',
    'installed/tests.xml', 'installed/campaign.json', 'installed/installed.json']
for name in selected:
    target = dest / 'after' / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(root / 'reports' / name, target)
for name in ('qualify.py', 'overlay.json', 'curate.py'):
    shutil.copyfile(root / name, dest / name)
campaign = json.loads((root / 'reports/installed/campaign.json').read_text())
assert campaign['status'] == 'PASS' and campaign['changed_inputs'] == []
cases = list(ET.parse(root / 'reports/installed/tests.xml').iter('testcase'))
assert len(cases) == 21 and all(not any(c.find(k) is not None for k in ['failure','error','skipped']) for c in cases)
overlay = json.loads((root / 'overlay.json').read_text())
assert all(sha(repo / n) == expected for n, expected in overlay.items())
summary = {'date': datetime.now(timezone.utc).isoformat(),
    'base_commit': subprocess.check_output(['git','rev-parse','HEAD'], cwd=repo, text=True).strip(),
    'snapshot': 'committed HEAD plus exactly the four paths in overlay.json; concurrent SVC07 edits excluded',
    'passed': 21, 'failed': 0, 'new_cases': 7, 'reused_cases': 14,
    'changed_inputs': [], 'cases': [dict(c.attrib) for c in cases],
    'qualification': ['actual occupied loopback listener owned by test parent; service launched as child',
        'actual invalid configuration, future migration and unavailable selected storage',
        'KeyboardInterrupt injected only in connect observer wait; real same-generation child remains alive',
        'child later reaches READY and canonical DRAINED with zero exit',
        'public diagnostic is coded; raw child stderr never used as public-cause proof'],
    'limits': ['Windows/Python3.13 installed packages; no real provider or native harness',
        'no Task Scheduler registration, login/logout/reboot or personal credentials',
        'initial raw reports retained under before; no failed result converted to pass',
        'Core and Connector wheels remain pre-SVC07 baseline; new drain work is not qualified here'],
    'redactions_in_new_artifacts': 0,
    'excluded': ['runtime homes and databases', 'raw child stderr', 'venv', 'wheel binary', 'pip install log']}
(dest / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
(dest / 'milestone.md').write_text('''# R3 — service startup boundaries

Occupied HTTP ports previously caused a real nonzero startup exit but exposed only
STARTUP_FAILED. The Server now records PORT_IN_USE (or BIND_FAILED for recognized
address/permission failures) in its bounded public lifecycle log. Classification
uses the actual asyncio listener exception and numeric errno, never arbitrary
exception text. No fallback endpoint/database and no takeover were added.

Only Nexus changed: serve.py, the log-code allowlist, seven new cases across two
test modules, and service documentation. No schema, wire or dependency change.
Rollback is the Nexus commit revert; this change writes only existing log records.

Before: the installed baseline ran seven cases, six passed and the occupied-port
public-diagnostic assertion failed. Earlier fixture/preparation failures remain
in before/ with their original results and manifest. After: **21 unique tests
passed** in a newly installed noneditable wheel environment: seven new cases and
14 reused log/lock cases. Core/Connector stayed at their qualified baseline wheel
hashes. The frozen snapshot excludes concurrent drain implementation work.

The canonical ci_installed.py runner verified installed bytes and unchanged test
inputs. package-proof.json compares all 690 Nexus payload files with the wheel,
installed files and frozen source; Core165 and Connector123 files match their
wheels. pip check and Ruff on the four changed code/test files passed. Commands,
distribution versions, XML, hashes and environment allowlist are retained.

SVC-T06/T12/T13 are verified for these Windows disposable-process contracts,
composed with the existing timeout observer test. Ctrl+C was injected at the
connect wait callback, not broadcast as a console signal; the actual service
owner remained unchanged and subsequently reached READY and DRAINED. This is
not a logon, logout, reboot, Task Scheduler, provider or full M1/M2 campaign.
No native service was registered and no personal vault/configuration was used.

SVC07 drain/explicit-force implementation remains the next dependency. Its new
three-repository payload must be built and qualified separately. The prior native
service proposal must be reconciled with that payload before any authorized run.
''', encoding='utf-8')
(dest / 'ruff.txt').write_text('python -m ruff check tests/test_service_failure_boundaries.py tests/test_service_bind_diagnostics.py src/okto_nexus/adapters/inbound/cli/serve.py src/okto_nexus/adapters/outbound/service_manager/logs.py\nAll checks passed!\n')
manifest = [{'path': p.relative_to(dest).as_posix(), 'bytes': p.stat().st_size, 'sha256': sha(p)}
    for p in sorted(dest.rglob('*')) if p.is_file()]
(dest / 'artifact-manifest.json').write_text(json.dumps({'artifacts': manifest,
    'all_files_except_this_manifest': True}, indent=2)+'\n')
ledger_path = repo / 'plans/agent_ops/ledger.json'
ledger = json.loads(ledger_path.read_text(encoding='utf-8'))
evidence = [relative + '/' + n for n in ['milestone.md','summary.json','after/installed/tests.xml','artifact-manifest.json']]
results = {
    'SVC-T06': 'Actual foreign occupied listener survives one failed detached startup; public PORT_IN_USE, same selected endpoint/database, no readiness, lock released. Installed fixed candidate passes.',
    'SVC-T12': 'Real invalid config, future migration ledger and blocked storage fail before readiness, preserve selected state and report cause; existing lock/bootstrap refusal tests also pass.',
    'SVC-T13': 'KeyboardInterrupt injected in connect observer wait preserves the same real owner/generation and does not repeat setup or stop service; owner then reaches READY and canonical DRAINED. Composes with retained timeout observer coverage.'}
for key, result in results.items():
    entry = ledger['scenarios'][key]
    entry.update(status='VERIFIED', result=result, remaining='None within the stated disposable Windows process scope.', remaining_kind='none')
    entry['evidence'] = sorted(set(entry['evidence'] + evidence))
ledger['updated_at'] = datetime.now(timezone.utc).isoformat()
ledger['history'].append({'date':'2026-11-07', 'milestone':'PR-10', 'status':'IN_PROGRESS',
    'summary':'Fixed actual occupied-port diagnostic gap with coded listener failure. 21 unique installed tests passed; SVC-T06/T12/T13 verified within disposable Windows scope. Historical 6pass/1productfailure retained. SVC07 and real service/provider campaigns remain pending.', 'evidence':evidence})
ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
paragraph = '''
## 2026-11-07 — R3: falhas de startup e interrupção da espera

Corrigido o diagnóstico público de porta ocupada: `PORT_IN_USE` no log limitado,
sem texto bruto da exceção nem troca de endpoint/banco. **21 testes instalados
passaram** em snapshot isolado: sete novos e14 reutilizados. Retidos os resultados
anteriores, incluindo6pass/1falha real. T06/T12/T13 verificados: porta realmente
ocupada, falhas reais de configuração/migração/storage e Ctrl+C injetado na espera
do connect com o mesmo processo vivo, depois READY/DRAINED. Nenhum serviço nativo,
provedor ou cofre pessoal utilizado. SVC07 e campanhas reais seguem pendentes.
Evidência: `plans/agent_ops/evidence/r3-service-boundaries/milestone.md`.
'''
for name in ['LEDGER_CODEX_NEXUS_INTEGRACAO_ATENCAO_ONBOARDING.md','plans/agent_ops/implementation-report.md']:
    with (repo / name).open('a', encoding='utf-8') as stream:
        stream.write(paragraph)
print(json.dumps({'evidence_files':len(manifest)+1, 'passed':21, 'updated_scenarios':list(results)}))
