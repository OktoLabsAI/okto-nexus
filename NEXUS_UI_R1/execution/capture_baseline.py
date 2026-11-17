"""Read-only repository inspection; no product imports or personal state reads."""
from pathlib import Path
import datetime
import hashlib
import json
import subprocess
import tomllib

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent


def git(repo, *args):
    return subprocess.check_output(
        ['rtk', 'proxy', 'git', *args], cwd=repo, text=True, encoding='utf-8'
    ).strip()


def main():
    manifest = json.loads((ROOT/'NEXUS_UI_R1/MANIFESTO.json').read_bytes())
    inputs = {}
    for item in manifest['files']:
        source = ROOT/'NEXUS_UI_R1'/item['name']
        data = source.read_bytes()
        assert len(data) == item['bytes']
        assert hashlib.sha256(data).hexdigest() == item['sha256'], source
        inputs[item['name']] = item['sha256']
    # The supplied manifest describes the INITIAL ledger, not its future edits.
    original = ROOT/'NEXUS_UI_R1/NEXUS_UI_EXECUTION_LEDGER_R1.json'
    preserved = OUT/'input-ledger.json'
    assert not preserved.exists(), 'Baseline must not overwrite its original input'
    preserved.write_bytes(original.read_bytes())
    refs = {
        'nexus': (ROOT, '3d95aad8c1b5d2e6354cd872512586fd7a02aec9'),
        'connector': (ROOT.parent/'okto-nexus-connector', 'a8bd48bdc6d6e835c55eb601a7e7fa316453aa7b'),
        'core': (ROOT.parent/'okto-nexus-connector-core', None),
    }
    repos = {}
    for name, (repo, reference) in refs.items():
        project = tomllib.loads((repo/'pyproject.toml').read_text(encoding='utf-8'))['project']
        repos[name] = {
            'path': str(repo), 'branch': git(repo, 'branch', '--show-current'),
            'head': git(repo, 'rev-parse', 'HEAD'), 'status': git(repo, 'status', '--short'),
            'version_before_bump': project['version'], 'dependencies': project.get('dependencies', []),
            'analysis_reference': reference,
        }
        if name != 'core':
            repos[name]['origin_main'] = git(repo, 'rev-parse', 'origin/main')
            repos[name]['main_commits_not_in_head'] = git(repo, 'log', '--format=%H %s', 'HEAD..origin/main')
        if reference:
            repos[name]['post_reference_commits'] = git(repo, 'log', '--format=%H %s', reference+'..HEAD')
            repos[name]['runtime_diff_from_reference'] = git(repo, 'diff', '--stat', reference, 'HEAD', '--', 'src', 'frontend', 'pyproject.toml', 'uv.lock')
    result = {'at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'input_hashes': inputs, 'original_ledger_copy': str(preserved.relative_to(ROOT)),
              'initial_observation': {'nexus_branch': 'feature/v0.3.4',
                  'nexus_head': '856c7f459d16719aa7dfa54c3dc64c85199cf563',
                  'nexus_status': '?? NEXUS_UI_R1/', 'connector_clean': True, 'core_clean': True},
              'repositories': repos,
              'effects': 'Only inspection and writing this evidence; no product/service/provider/authentication action.'}
    (OUT/'baseline.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print('Baseline captured; four supplied hashes verified; original ledger preserved.')


if __name__ == '__main__':
    main()
