"""Curate only this proposal's declared public files; no runtime state."""
from pathlib import Path
import hashlib
import json
import re

PUBLIC = Path(__file__).resolve().parent
md = PUBLIC / 'm1-codex-campaign-proposal.md'
value = md.read_text(encoding='utf-8')
replacements = {
    'oficial0.157.0': 'oficial 0.157.0', 'tem322525488bytes': 'tem 322525488 bytes',
    'O0.167.0': 'O 0.167.0', 'O0.159.0': 'O 0.159.0', 'alpha0.159.0': 'alpha 0.159.0',
    'contendo1,2,3,4': 'contendo 1, 2, 3, 4', 'contagem4, soma10': 'contagem 4, soma 10',
    'é6admissões': 'é 6 admissões', 'de200000tokens': 'de 200000 tokens',
    'após100000tokens': 'após 100000 tokens', 'após120000ou120s': 'após 120000 tokens ou 120 s',
    'Se200000for': 'Se 200000 for', 'O agente não leu, copiará ou divulgará': 'O agente não leu e não copiará nem divulgará',
    'ou0.167.0': 'ou 0.167.0', 'M1/DX-T39local': 'M1/DX-T39 local',
    'M1/DX-T40Connector': 'M1/DX-T40 Connector', 'DX-T43contexto': 'DX-T43 contexto',
    'DX-T45decisão': 'DX-T45 decisão', 'DX-T46perda': 'DX-T46 perda',
    'DX-T47retorno': 'DX-T47 retorno', 'DX-T50sem': 'DX-T50 sem',
}
for before, after in replacements.items():
    value = value.replace(before, after)
md.write_text(value, encoding='utf-8', newline='\n')
attempt = {
    'exit_code': 2, 'phase': 'legacy_portable_identity_comparison',
    'cause': 'The downloaded executable SHA equals the exact qualified fingerprint, but current v3 portable identity differs from the historical portable grant. Initial proof is retained unmodified. A separate pure current-Core check confirms the exact fingerprint route qualifies conversation/controls; no allowlist was changed.',
    'initial_proof': 'codex-0.157.0-artifact-proof.json',
    'final_proof': 'codex-0.157.0-pure-qualification.json',
    'native_executions': 0,
}
(PUBLIC / 'preparation-attempt-03.json').write_text(json.dumps(attempt, indent=2) + '\n', encoding='utf-8')
allowlist = [
    'prepare_official_artifact_initial.py', 'prepare_official_artifact_attempt02.py',
    'prepare_official_artifact.py', 'verify_official_artifact.py', 'build_proposal.py',
    'finalize_public.py', 'preparation-attempt-01.json', 'preparation-attempt-02.json',
    'preparation-attempt-03.json', 'codex-0.157.0-artifact-proof.json',
    'codex-0.157.0-pure-qualification.json', 'm1-codex-campaign-proposal.json',
    'm1-codex-campaign-proposal.md',
]
files = []
for name in allowlist:
    payload = (PUBLIC / name).read_bytes()
    assert not re.search(rb'nxs_[A-Za-z0-9_-]{24,}', payload), name
    if name.endswith('.json'):
        json.loads(payload)
    files.append({'path': name, 'bytes': len(payload), 'sha256': hashlib.sha256(payload).hexdigest()})
aggregate = hashlib.sha256(json.dumps(files, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
manifest = {
    'format': 'okto.m1.proposal-public-manifest', 'revision': 1,
    'status': 'PREPARATION_ONLY', 'files': files, 'aggregate_sha256': aggregate,
    'raw_artifacts_excluded': ['../artifacts/codex-x86_64-pc-windows-msvc.exe.zip', '../artifacts/codex-0.157.0-windows-x64/', '../artifacts/github-release-metadata.json'],
    'native_executions': 0, 'inference_calls': 0, 'secrets_read_or_copied': False,
    'test_suites_executed': 0, 'redactions': 0,
    'limits': ['Hashes cover preparation documents/scripts and file bytes, not final SVC07 wheels.', 'No campaign acceptance or native liveness/authentication claim.', 'Strict token-cap and final execution authorization remain open.'],
}
(PUBLIC / 'artifact-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'public': str(PUBLIC), 'artifact_count': len(files), 'aggregate_sha256': aggregate, 'proposal_sha256': next(x['sha256'] for x in files if x['path'] == 'm1-codex-campaign-proposal.json'), 'manifest_sha256': hashlib.sha256((PUBLIC / 'artifact-manifest.json').read_bytes()).hexdigest()}))
