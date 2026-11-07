"""Append final EOF-only package evidence; preserve all earlier raw attempts."""
import ast
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile

BASE = Path(__file__).parent
REPO = Path(r'D:/Projetos/Techridy/okto_labs_okto_nexus')
REL = 'plans/agent_ops/evidence/pr03-remote-bootstrap'
DEST = REPO / REL
candidate = BASE / 'candidate-v3'
proof = json.loads((candidate / 'package-proof.json').read_text())
initial = json.loads((DEST / 'candidate-v1/package-proof.json').read_text())
formatted = json.loads((BASE / 'product-format-equivalence.json').read_text())
for name, package in proof['packages'].items():
    root = Path(package['repository']) / 'src' / name
    actual = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc', '.pyo')}
    assert actual == package['files']
    previous = initial['packages'][name]
    assert actual.keys() == previous['files'].keys()
    changed = [key for key in actual if actual[key] != previous['files'][key]]
    assert changed == (['application/remote_setup_contract.py'] if name == 'okto_nexus' else [])
    if changed:
        key, = changed
        assert previous['files'][key] == formatted['before_sha256']
        assert actual[key] == formatted['after_sha256']
        with zipfile.ZipFile(previous['wheel']) as archive:
            before = archive.read(name + '/' + key)
        after = (root / key).read_bytes()
        assert before.rstrip(b'\r\n') == after.rstrip(b'\r\n')
        assert ast.dump(ast.parse(before)) == ast.dump(ast.parse(after))
assert proof['core_sha256'] == initial['core_sha256']
assert proof['packages']['okto_nexus_connector']['wheel_sha256'] == initial['packages']['okto_nexus_connector']['wheel_sha256']

def copy(source, relative):
    target = DEST / relative
    assert not target.exists(), relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)

for name in ('package-proof.json', 'okto_nexus-build.log', 'okto_nexus_connector-build.log', 'venv-create.log', 'wheel-install.log'):
    copy(candidate / name, 'candidate-v3/' + name)
for name in ('installed.xml', 'qualification.json'):
    copy(candidate / 'tests-nexus-final-contract' / name, 'candidate-v3/nexus/' + name)
copy(BASE / 'candidate-v2/okto_nexus-build.log', 'candidate-v2/okto_nexus-build.log')
copy(BASE / 'product-format-equivalence.json', 'static/product-format-equivalence.json')
for source, name in [('build_candidate.py', 'build_candidate_final.py'),
                     ('finalize_whitespace.py', 'finalize_whitespace.py'),
                     ('append_final_candidate.py', 'append_final_candidate.py'),
                     ('nexus-final-nodes.json', 'nexus-final-nodes.json')]:
    copy(BASE / source, 'drivers/' + name)
reports_path = DEST / 'reports.json'
copy(reports_path, 'reports-initial.json')
reports = json.loads(reports_path.read_text())
relative = 'candidate-v3/nexus/installed.xml'
raw = (DEST / relative).read_bytes()
tree = ET.fromstring(raw)
rows = list(tree.iter('testcase'))
final = dict(sha256=hashlib.sha256(raw).hexdigest(), tests=len(rows),
    failures=sum(x.find('failure') is not None for x in rows),
    errors=sum(x.find('error') is not None for x in rows), skips=sum(x.find('skipped') is not None for x in rows),
    unique_identities=len({(x.get('classname'), x.get('name')) for x in rows}),
    suites=[dict(s.attrib) for s in tree.iter('testsuite')])
assert final['tests'] == 35 and final['failures'] == final['errors'] == final['skips'] == 0
reports['reports'][relative] = final
runs = reports['installed']['nexus']['runs'] + [relative]
latest = {}
observations = 0
for path in runs:
    for row in ET.parse(DEST / path).getroot().iter('testcase'):
        observations += 1
        latest[(row.get('classname'), row.get('name'))] = row
assert len(latest) == 187 and all(not any(row.find(k) is not None for k in ('failure', 'error', 'skipped')) for row in latest.values())
reports['installed']['nexus'].update(runs=runs, observations=observations,
    overlapping_identities=observations-len(latest), final_contract_tests=35,
    package_equivalence='candidate-v3 differs from candidate-v1 only by two removed trailing CRLFs in one Python file; exact AST equivalence retained')
reports['final_candidate'] = dict(nexus='candidate-v3', connector='candidate-v1 (same wheel reused)',
    proof='candidate-v3/package-proof.json', product_format_equivalence='static/product-format-equivalence.json',
    failed_build='candidate-v2 lacked setuptools in its selected build interpreter; no wheel produced; standard build interpreter used for candidate-v3')
reports_path.write_text(json.dumps(reports, indent=2), encoding='utf-8')

old_sha = initial['packages']['okto_nexus']['wheel_sha256']
new_sha = proof['packages']['okto_nexus']['wheel_sha256']
docpath = REPO / 'plans/agent_ops/evidence/pr03-remote-bootstrap.md'
doc = docpath.read_text(encoding='utf-8').replace(old_sha, new_sha)
note = ('Final packaging correction: the staged whitespace check found two redundant CRLFs at EOF in '
    '`application/remote_setup_contract.py`. Only those bytes were removed; the retained AST and all other '
    '689 Nexus file hashes are unchanged. Candidate-v3 contains the exact final 690 source files and reuses '
    'the already-qualified Connector and Core wheels. Its 35 Server/HTTP/guard cases pass outside the checkout. '
    'The broader 187-case qualification above used candidate-v1; these 35 overlapping final-package cases '
    'are not added as new identities. Candidate-v2 produced no wheel because the selected source-test interpreter '
    'lacked setuptools; its build log remains retained, and the standard build interpreter succeeded. '
    'See `candidate-v3/package-proof.json`, `candidate-v3/nexus/qualification.json` and '
    '`static/product-format-equivalence.json`. Final staged whitespace checks pass.\n\n')
doc = doc.replace('The six joint cases cover', note + 'The six joint cases cover')
docpath.write_text(doc, encoding='utf-8')
evidence = [REL + '/candidate-v3/package-proof.json', REL + '/candidate-v3/nexus/installed.xml',
    REL + '/candidate-v3/nexus/qualification.json', REL + '/static/product-format-equivalence.json']
ledger_path = REPO / 'plans/agent_ops/ledger.json'
ledger = json.loads(ledger_path.read_text(encoding='utf-8'))
for section in ('tasks', 'scenarios', 'completion_criteria'):
    for item in ledger[section].values():
        field = 'tests' if section == 'tasks' else 'evidence'
        if REL + '/reports.json' in item.get(field, []):
            item[field] = sorted(set(item[field] + evidence))
ledger['milestones']['PR-03']['evidence'] = sorted(set(ledger['milestones']['PR-03']['evidence'] + evidence))
campaign = ledger['campaigns']['pr03_remote_bootstrap_windows_loopback']
campaign['evidence'] = sorted(set(campaign['evidence'] + evidence))
campaign['final_package_note'] = 'Final Nexus candidate-v3 removes only two trailing CRLFs; AST unchanged; 35 overlapping installed contract tests passed. Initial 187 identities remain qualified with retained raw attempts.'
campaign['final_nexus_wheel_sha256'] = new_sha
ledger['history'][-1]['evidence'] = sorted(set(ledger['history'][-1]['evidence'] + evidence))
ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
with (REPO / 'LEDGER_CODEX_NEXUS_INTEGRACAO_ATENCAO_ONBOARDING.md').open('a', encoding='utf-8') as stream:
    stream.write('\nPacote Nexus final: remoção apenas de duas quebras vazias no EOF, com AST equivalente; '
        '35 testes instalados de contrato/HTTP/guards passaram novamente, sem somá-los aos 187 casos únicos. '
        'A evidência anterior e a tentativa de build sem setuptools foram preservadas.\n')
subprocess.run(['git', 'diff', '--check'], cwd=REPO, check=True)
print(json.dumps(dict(final_nexus_wheel=new_sha, final_tests=35, unique_nexus_tests=187,
    connector_unchanged=True, source_equivalence_verified=True)))
