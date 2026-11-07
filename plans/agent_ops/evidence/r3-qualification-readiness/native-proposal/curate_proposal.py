"""Retain public preparation proofs; no venv, wheels, homes, tasks or campaign."""
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
DEST = ROOT / 'public-proposal'
DEST.mkdir(exist_ok=False)


def sha(data):
    return hashlib.sha256(data).hexdigest()


diagnostic = dict(status='PREPARATION_DIAGNOSTIC_ONLY', original_driver='prepare_proposal.py',
    observed_exit_code=1, failing_line=102, condition='assert clean', completed_readonly_checks=8,
    checks_successfully_completed=['installed imports/source-wheel byte check and exactly two Task Scheduler reads',
        'pythonw isolated imports', 'six CLI --help invocations'],
    pending_nonproduct_changes=['vendor/ci/manifest.json', 'vendor/ci/okto_nexus_connector-0.0.12-py3-none-any.whl'],
    observed_error='AssertionError', outcome_source='Observed tool exit/trace transcribed; no raw stderr file was created for the orchestration process.',
    correction='Separate finalize_proposal.py reused completed reports and recorded nonproduct CI edits; original driver unchanged.',
    native_campaign_actions_executed=0, no_checks_repeated=True)
with (ROOT / 'preparation-diagnostic.json').open('x', encoding='utf-8') as output:
    json.dump(diagnostic, output, indent=2)
files = sorted(path for path in ROOT.iterdir() if path.is_file() and path.suffix in ('.py', '.json', '.txt', '.log'))
assert all(not re.search(rb'\b(?:nxs_|nxobs_|nxsept_|nxt4_|nxc4_)[A-Za-z0-9_-]{20,}\b', path.read_bytes()) for path in files)
artifacts = []
for path in files:
    data = path.read_bytes()
    with (DEST / path.name).open('xb') as output:
        output.write(data)
    artifacts.append(dict(path=path.name, source_path=str(path), sha256=sha(data), bytes=len(data), byte_exact=True))
proposal = json.loads((ROOT / 'native-service-campaign-proposal.json').read_text())
old = Path('D:/Projetos/Techridy/okto_labs_okto_nexus/plans/agent_ops/evidence/pr02-native-campaign-plan.json')
manifest = dict(status='PREPARED_NOT_AUTHORIZED_NOT_RUN', revision=2, artifact_count=len(artifacts),
    proposal_sha256=sha((ROOT / 'native-service-campaign-proposal.json').read_bytes()),
    aggregate_sha256=sha(json.dumps({item['path']:item['sha256'] for item in artifacts}, sort_keys=True, separators=(',', ':')).encode()),
    prior_proposal=dict(path=str(old), sha256=sha(old.read_bytes()), unchanged=True),
    task_names=proposal['task_names'], campaign_actions_executed=0, native_preparation_calls='two exact-name read calls only',
    exclusions=['No data homes, DB/WAL, venv, dependency or product wheel binaries, key/token/cookie material copied.'],
    artifacts=artifacts)
with (DEST / 'artifact-manifest.json').open('x', encoding='utf-8') as output:
    json.dump(manifest, output, indent=2)
for item in artifacts:
    assert sha((DEST / item['path']).read_bytes()) == item['sha256'] == sha(Path(item['source_path']).read_bytes())
print(json.dumps(dict(destination=str(DEST), artifact_count=len(artifacts),
    proposal_sha256=manifest['proposal_sha256'], aggregate_sha256=manifest['aggregate_sha256'],
    manifest_sha256=sha((DEST / 'artifact-manifest.json').read_bytes()), verified=True), indent=2))
