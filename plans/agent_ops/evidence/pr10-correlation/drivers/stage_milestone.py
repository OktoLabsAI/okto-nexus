"""Stage only the reviewed PR10b paths after artifact closure."""
import json
from pathlib import Path
import subprocess

BASE = Path(__file__).resolve().parent
REPO = Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
evidence = 'plans/agent_ops/evidence/pr10-correlation'
assert (REPO / evidence / 'artifact-manifest.json').is_file()
reports = json.loads((REPO / evidence / 'reports.json').read_text(encoding='utf-8'))
assert reports['collection_phase'] == 'closed_qualified_milestone'
ruff = json.loads((BASE / 'changed-python-ruff-final.json').read_text(encoding='utf-8'))
assert ruff['exit_code'] == 0
paths = sorted(set(ruff['paths'] + [
    '.gitattributes', 'LEDGER_CODEX_NEXUS_INTEGRACAO_ATENCAO_ONBOARDING.md',
    'docs/external-observations.md', 'docs/terminal-doctor.md',
    'frontend/src/components/CanonicalObservation.tsx',
    'frontend/src/components/ExternalObservations.tsx',
    'frontend/src/observationTypes.ts',
    'frontend/tests/observationContract.types.ts',
    'frontend/tests/observationCorrelation.test.mjs',
    'plans/agent_ops/ledger.json', 'plans/agent_ops/implementation-report.md',
    'plans/agent_ops/evidence/pr10-diagnostics-connector.md',
    'plans/agent_ops/evidence/pr10-diagnostics-nexus.md',
    evidence + '.md', evidence,
    'src/okto_nexus/migrations/166_observation_correlations.sql',
    'src/okto_nexus/adapters/inbound/http/static/index.html',
    'src/okto_nexus/adapters/inbound/http/static/assets/index-kTkLvZ6j.js',
    'src/okto_nexus/adapters/inbound/http/static/assets/index-OzUGF4xp.js',
    'tests/fixtures/diagnostics_v1',
]))
staged = subprocess.check_output(['git', 'diff', '--cached', '--name-only', '-z'], cwd=REPO)
assert not staged, 'Unexpected preexisting staged paths'
result = subprocess.run(['git', 'add', '--', *paths], cwd=REPO, capture_output=True, text=True)
(BASE / 'stage-result.json').write_text(json.dumps(dict(paths=paths,
    exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr), indent=2), encoding='utf-8')
assert result.returncode == 0, result.stderr
actual = subprocess.check_output(['git', 'diff', '--cached', '--name-only', '-z'], cwd=REPO).decode().strip('\0').split('\0')
assert all(name in paths or name.startswith((evidence + '/', 'tests/fixtures/diagnostics_v1/')) for name in actual)
assert not any(name.startswith('plans/agent_ops/evidence/pr10-external/') for name in actual)
print(json.dumps(dict(staged_paths=len(actual), explicit_pathspecs=len(paths)), indent=2))
