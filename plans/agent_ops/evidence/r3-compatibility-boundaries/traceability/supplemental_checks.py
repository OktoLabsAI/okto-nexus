import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
OUT = Path(__file__).parent
E = 'plans/agent_ops/evidence/'
sha = lambda b: hashlib.sha256(b).hexdigest()

def load(p):
    return json.loads((ROOT / p).read_text(encoding='utf-8'))

scan = load(E + 'r3-public-artifact-review/scan-after.json')
herdr = []
for name, classification in (
    ('collect_artifacts.py', 'Expected closure/verification driver; collector generates the 142-entry manifest and is cited separately by pr09-herdr.md:47.'),
    ('initial-manifest.json', 'Expected historical manifest of 316 unique source tests/11 initial reports; retained independently by collector lines143-151. Not an untracked runtime artifact.'),
):
    path = E + 'pr09-herdr/' + name
    item = {'path': path, 'classification': classification, 'bytes': (ROOT / path).stat().st_size, 'sha256': sha((ROOT / path).read_bytes())}
    matches = []
    def find(value):
        if isinstance(value, dict):
            if value.get('path') == path:
                matches.append(value)
            if path in value:
                matches.append({'path': path, 'record': value[path]})
            for v in value.values(): find(v)
        elif isinstance(value, list):
            for v in value: find(v)
    find(scan['inventory'])
    item['public_review_inventory_matches'] = matches
    herdr.append(item)

payloads = []
proof = load(E + 'pr04-participant-guide/installed/candidate-v1/package-proof.json')
for repo, module, wheel in (
    (ROOT, 'okto_nexus', Path(proof['wheel'])),
    (Path('D:/Projetos/Techridy/okto-nexus-connector'), 'okto_nexus_connector', ROOT / 'vendor/ci/okto_nexus_connector-0.0.12-py3-none-any.whl'),
    (Path('D:/Projetos/Techridy/okto-nexus-connector-core'), 'nexus_connector_core', ROOT / 'vendor/wheels/okto_nexus_connector_core-0.0.14-py3-none-any.whl'),
):
    source_root = repo / 'src' / module
    source_names = {p.relative_to(source_root).as_posix() for p in source_root.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc'}
    with zipfile.ZipFile(wheel) as z:
        names = {p[len(module)+1:] for p in z.namelist() if p.startswith(module + '/') and not p.endswith('/')}
    extensions = {}
    for p in names:
        extensions[Path(p).suffix] = extensions.get(Path(p).suffix, 0) + 1
    payloads.append({'module': module, 'source_files': len(source_names), 'wheel_files': len(names), 'source_files_missing_from_wheel': sorted(source_names - names), 'wheel_files_not_in_source': sorted(names - source_names), 'extensions': extensions})

ledger = json.loads(subprocess.check_output(['rtk', 'proxy', 'git', '-C', str(ROOT), 'show', '5545dbde:plans/agent_ops/ledger.json']))
all_evidence = set()
def collect(v):
    if isinstance(v, dict):
        evidence = v.get('evidence')
        if isinstance(evidence, list):
            all_evidence.update(p for p in evidence if isinstance(p, str))
        for child in v.values(): collect(child)
    elif isinstance(v, list):
        for child in v: collect(child)
collect(ledger)
missing = sorted(p for p in all_evidence if not (ROOT / p).exists())
result = {'herdr_supplemental_inventory': herdr, 'payload_completeness': payloads,
          'all_explicit_ledger_evidence_lists': {'unique': len(all_evidence), 'missing': missing},
          'public_review_followup': {'commit': 'bcf0e8aa', 'read_files': {p: sha((ROOT / p).read_bytes()) for p in [E+'r3-public-artifact-review/milestone.md', E+'r3-public-artifact-review/scan-after.json', E+'r3-public-artifact-review/verification.json']}, 'no_values_copied': True},
          'pending_campaign_document_update': {'path': 'plans/agent_ops/campaigns/windows-user-service.md', 'worktree_sha256': sha((ROOT/'plans/agent_ops/campaigns/windows-user-service.md').read_bytes()), 'proposal_sha256': sha((ROOT/(E+'r3-qualification-readiness/native-proposal/native-service-campaign-proposal.json')).read_bytes()), 'status': 'Read updated working-tree document; parent owns pending publication. Native campaign remains NOT_AUTHORIZED_NOT_RUN.'}}
(OUT/'supplemental-checks.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))
