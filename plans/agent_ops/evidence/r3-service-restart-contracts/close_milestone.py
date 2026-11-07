from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import re
import shutil
import sys
import xml.etree.ElementTree as ET

repo = Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
temp = Path('C:/Users/jpamb/AppData/Local/Temp')
root = temp/'r3-cooperative-drain-09ucmgsr'
installed = root/'nexus-service-restart-contracts'
target = repo/'plans/agent_ops/evidence/r3-service-restart-contracts'
assert len(sys.argv) == 3, 'T22 public allowlist and exact installed pytest root required'
child_public, pytest_root = map(Path, sys.argv[1:])
result = json.loads((installed/'result.json').read_text())
campaign = json.loads((installed/'canonical/campaign.json').read_text())
assert result['exit'] == 0 and result['cases'] == 4 and not result['failures'] and not result['skips']
assert campaign['status'] == 'PASS' and campaign['changed_inputs'] == []
assert (installed/'pip-check.txt').read_text().strip() == 'No broken requirements found.'
cases = list(ET.parse(installed/'canonical/tests.xml').iter('testcase'))
assert len(cases) == 4 and all(c.find(t) is None for c in cases for t in ('failure','error','skipped'))
source_proof = json.loads((root/'service-restart-source-proof.json').read_text())
for item in source_proof['cases']:
    assert hashlib.sha256((repo/item['test']).read_bytes()).hexdigest() == item['sha256']
    assert (repo/item['test']).read_bytes() == (root/'nexus-source-v1'/item['test']).read_bytes()
for directory in (temp/'svc-t23-t24-source-ceueozkh/public-v2', child_public, temp/'r3-svc22-rg05-audit-m5xy8nc9/public'):
    manifest_path = directory/('manifest.json' if (directory/'manifest.json').exists() else 'artifact-manifest.json')
    manifest = json.loads(manifest_path.read_text())
    entries = manifest.get('files')
    if entries is None:
        entries = {item['path']: {'sha256': item['artifact_sha256']} for item in manifest['artifacts']}
    for name, metadata in entries.items():
        assert hashlib.sha256((directory/name).read_bytes()).hexdigest() == metadata['sha256'], name
assert not target.exists()
target.mkdir()
locations = {}
def copy(source, relative):
    destination = target/relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(source.read_bytes())
    locations[str(source)] = dict(published_path=destination.relative_to(repo).as_posix(),
                                 sha256=hashlib.sha256(source.read_bytes()).hexdigest())

for source, subdir in [
    (temp/'svc-t23-t24-source-ceueozkh/public-v2', 'source-restart'),
    (child_public, 'source-child'),
    (temp/'r3-svc22-rg05-audit-m5xy8nc9/public', 'recovery-audit'),
]:
    for p in source.rglob('*'):
        if p.is_file(): copy(p, Path(subdir)/p.relative_to(source))
for p in installed.rglob('*'):
    if p.is_file() and p.suffix in {'.json','.xml','.txt'}: copy(p, Path('installed')/p.relative_to(installed))
for name in ('qualify_service_restart.py','service-restart-source-proof.json'):
    copy(root/name, name)
copy(temp/'prepare_service_restart_qualification.py', 'prepare_service_restart_qualification.py')
copy(temp/'svc-t23-t24-source-ceueozkh/t22-readonly-review.json', 't22-readonly-review.json')
copy(Path(__file__), 'close_milestone.py')
proofs = []
for directory in pytest_root.iterdir():
    if not directory.is_dir() or not re.search(r'\d+$', directory.name): continue
    for name in ('owner-proofs.json', 'owned-child-proof.json'):
        path = directory/name
        if path.exists():
            assert path.stat().st_mtime >= datetime.fromisoformat(campaign['started_at']).timestamp()
            proof = json.loads(path.read_text())
            if name == 'owned-child-proof.json':
                assert proof['completed'] and proof['physical_release_confirmed']
                assert proof['child_exit_code'] == 0 and proof['physical_work_records'] == 1
                assert not proof['slot_before_release']['released'] and proof['slot_after_release']['released']
                assert proof['server_owner_exited'] and not proof['automatic_replacement_started']
            elif len(proof) == 2:
                assert proof[0]['state'] == 'crashed_owner_exited'
                assert proof[1]['state'] == 'canonically_drained_owner_exited'
                assert proof[0]['instance_id'] == proof[1]['instance_id']
                assert all(proof[0][key] != proof[1][key] for key in ('pid','birth','generation'))
            else:
                assert len(proof) == 1 and proof[0]['state'] == 'ready'
            copy(path, Path('installed-owners')/directory.name/name)
            proofs.append(dict(path=directory.name+'/'+name, data=proof))
assert len(proofs) == 5
(target/'evidence-location-map.json').write_text(json.dumps(locations, indent=2)+'\n')
prefix = target.relative_to(repo).as_posix()
rows = {
 'SVC-T22': 'Current installed restart attempt with a real Core-owned Python child stays pending; canonical Server owner/generation, birth, claim and slot remain. One physical effect; explicit close yields child exit0, release, DRAINED and no implicit replacement. Retained NS14-01 separately proves uncertain-operation restart at its historical wheel scope.',
 'SVC-T23': 'Three current installed real Server crash/return cases preserve installation identity, bindings, permissions and limits. Expired/revoked grants remain invalid; valid control admits only new explicit work. Canonical HANDLE birth/death and distinct replacement generation are proved.',
 'SVC-T24': 'Same live Connector reconnects to the actual replacement Server without another executor, identity, Finish, probe or old productive effect. Previous work and native session were closed before the crash; active-session survival is not claimed.',
 'RG-05': 'Explicit new-flow inventory and39 current retained recovery identities, AC05 complementary receipt/process-death proofs and4 new installed lifecycle cases support no implicit replay. Historical uncertain-operation Server restart remains labeled historical; no new provider or OS suspension acceptance is inferred.',
}
limits = ['Windows process qualification; native provider behavior is synthetic.',
          'No paid inference, personal credentials, Task Scheduler registration, logout, reboot or suspension was performed.',
          'T22 child belongs to Core in the live Connector. No child survival after its owner dies is claimed.',
          'Four unique new cases ran once in each final source and installed qualification, not eight independent scenarios.',
          'Earlier fixture failures and the redirector-based superseded PASS remain in the immutable source history.']
(target/'qualification.json').write_text(json.dumps(dict(status='VERIFIED', source_cases=4,
    installed_cases=4, unique_new_cases=4, cases=[c.attrib for c in cases],
    product_changes=0, scenarios=rows, limits=limits,
    packages=json.loads((installed/'package-proof.json').read_text())),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
ledger_path = repo/'plans/agent_ops/ledger.json'
ledger = json.loads(ledger_path.read_text(encoding='utf-8'))
for key, explanation in rows.items():
    item = ledger['scenarios'][key]
    item.update(status='VERIFIED', result=explanation, remaining='None within this literal contract and recorded qualification scope.', remaining_kind='none')
    item['qualification_limit'] = limits
    item['evidence'] = sorted(set(item.get('evidence', []) + [prefix+'/qualification.json', prefix+'/artifact-manifest.json', prefix+'/installed/canonical/tests.xml']))
ledger['campaigns']['r3_service_restart_contracts'] = dict(status='VERIFIED', unique_new_cases=4,
    source_cases=4, installed_cases=4, product_changes=0, evidence=[prefix+'/qualification.json',prefix+'/artifact-manifest.json'])
ledger['updated_at'] = datetime.now(timezone.utc).isoformat()
ledger['history'].append(dict(date='2026-11-07',milestone='Service restart and owned child contracts',status='VERIFIED',
    summary='SVC-T22/T23/T24 and RG-05 contract predicates qualified; four new source and four installed PASS. M1/native service/platform campaigns remain open.',evidence=[prefix+'/qualification.json']))
ledger_path.write_text(json.dumps(ledger,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
note = '''
## 2026-11-07 — reinício e ownership de processos

Quatro novos casos passaram no código-fonte e nos pacotes instalados atuais.
SVC-T22/T23/T24 e RG-05 foram verificados no escopo literal: reinício pendente
preserva o filho real, claim e slot; queda/retorno do Server preserva vínculos,
limites e grants e não repete trabalho. A prova usa PID canônico, nascimento,
geração e saída do processo real. O filho fecha com exit0 antes da liberação.
As tentativas de preparação e o PASS invalidado por PID do redirector estão
preservados; não contam como cobertura nova. Não houve mudança de produto,
inferência real ou Task Scheduler. M1 e campanhas de plataforma seguem abertos.
Evidência: `plans/agent_ops/evidence/r3-service-restart-contracts/qualification.json`.
'''
for name in ('LEDGER_CODEX_NEXUS_INTEGRACAO_ATENCAO_ONBOARDING.md','plans/agent_ops/implementation-report.md'):
    with (repo/name).open('a',encoding='utf-8') as f: f.write(note)
(target/'milestone.md').write_text('# Service restart contracts\n\n'+'\n\n'.join(rows.values())+'\n\n'+'\n'.join('- '+v for v in limits)+'\n',encoding='utf-8')
with (repo/'.gitattributes').open('a',encoding='utf-8') as f: f.write(prefix+'/** -text -whitespace\n')
patterns = [rb'\b(?:nxs_|nxobs_|nxsept_|nxt4_|nxc4_)[A-Za-z0-9_-]{20,}', rb'\b(?:sk-proj-|sk-ant-|sk-)[A-Za-z0-9_-]{24,}',rb'\b(?:ghp_|github_pat_)[A-Za-z0-9_]{25,}',rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----']
findings = []
for p in target.rglob('*'):
    if p.is_file():
        for pattern in patterns:
            findings += [dict(path=p.relative_to(target).as_posix(), sha256=hashlib.sha256(m.group()).hexdigest()) for m in re.finditer(pattern,p.read_bytes())]
assert not findings, findings
(target/'public-review.json').write_text(json.dumps(dict(findings=findings,scope='Finite allowlist and qualification runner output; no private child/server logs, databases, homes or provider secrets copied'),indent=2)+'\n')
files = {p.relative_to(target).as_posix():dict(sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size) for p in sorted(target.rglob('*')) if p.is_file()}
(target/'artifact-manifest.json').write_text(json.dumps(dict(files=files,scope='Exact public bytes; nested source manifests remain immutable'),indent=2)+'\n')
print(json.dumps(dict(closed=list(rows), unique_new_cases=4, artifacts=len(files))))
