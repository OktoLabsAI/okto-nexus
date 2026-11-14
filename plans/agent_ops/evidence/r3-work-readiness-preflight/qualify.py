from pathlib import Path
import hashlib
import json
import xml.etree.ElementTree as ET

B = Path(__file__).resolve().parent
REPO = Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
PATHS = ['src/okto_nexus/adapters/inbound/cli/work.py',
         'src/okto_nexus/adapters/outbound/service_manager/inspection.py',
         'tests/test_work_readiness_preflight.py']


def pin(path):
    raw = path.read_bytes()
    return dict(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))


def suite(name):
    root = ET.parse(B / name).getroot()
    values = [root] if root.tag == 'testsuite' else list(root.iter('testsuite'))
    return {key: sum(int(node.get(key, '0')) for node in values)
            for key in ('tests', 'failures', 'errors', 'skipped')}


for rel in PATHS:
    target = B / 'final' / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes((REPO / rel).read_bytes())

document = dict(
    status='SOURCE_QUALIFIED_NOT_INSTALLED_OR_ACTUAL',
    source={rel: pin(REPO / rel) for rel in PATHS},
    initial_regression=dict(results=suite('source.xml'), pins='initial-pins.json',
        limitation='Loaded intermediate default=2 total-budget implementation; rejected in review because original two seconds bound HTTP only. Preserved as antecedent, not final-default proof.'),
    final_delta=dict(results=suite('final-delta.xml'),
        scope='Final explicit-only retry/defaultNone compatibility, inspection classification, CLI single-dispatch/drain/lock and remote authorization uncertainty.'),
    inherited_regressions='Initial source suite also exercised terminal work, authorization and remote operator behavior; fixtures reverted byte-for-byte once final default restored the original single inspect() contract.',
    checks=dict(ruff='PASS', git_diff_check='PASS', root_review='Initial diff reviewed; required defaultNone compatibility delta implemented.', peer_review='v11_preparation read-only approved final defaultNone delta'),
    contract=dict(default='one canonical inspect(), existing HTTP timeout 2; no added total deadline',
        explicit_readiness_seconds='0 < selection <= 30', per_http_seconds=2,
        remote='single existing inspect() verification; no local lifecycle effects',
        watch_chat_timeout='unchanged', dispatch_retry=False, start=False,
        effect_before_ready=False, owner_hint_is_readiness_proof=False),
    limitations=['No historical root-cause inference from SERVICE_UNREACHABLE.',
        'Initial regression: 122 passed in 646.18 seconds; one existing Starlette/httpx deprecation warning. Final delta: 76 passed in 17.56 seconds. Suites overlap and are not summed as distinct cases.',
        'Explicit monotonic budget rejects late readiness but cannot preempt Scheduler or OS I/O.',
        'No installed wheel or actual campaign claim; no change to M1 600-second or monitor bounds.'],
)
(B / 'qualification.json').write_text(json.dumps(document, indent=2) + '\n', encoding='utf-8')
public = ['run_source.py', 'run_final_delta.py', 'qualify.py', 'initial-pins.json',
          'source.xml', 'final-delta.xml', 'qualification.json']
public += [p.relative_to(B).as_posix() for d in ('initial', 'final') for p in (B / d).rglob('*.py')]
(B / 'public-allowlist.json').write_text(json.dumps(dict(files=[
    dict(path=rel, **pin(B / rel)) for rel in sorted(public)]), indent=2) + '\n', encoding='utf-8')
print(json.dumps(dict(qualification=pin(B / 'qualification.json'),
                     allowlist=pin(B / 'public-allowlist.json'),
                     initial=document['initial_regression']['results'], final=document['final_delta']['results'])))
