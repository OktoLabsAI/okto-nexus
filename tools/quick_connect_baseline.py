"""Freeze the supplied Quick Connect specification and record this checkout."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = Path(r'C:\Users\jpamb\Downloads\NEXUS_QUICK_CONNECT_R1_CONSOLIDADO_PACOTE_CODEX')
OUT = ROOT / 'NEXUS_QUICK_CONNECT_R1'


def git(repo, *args):
    result = subprocess.run(['rtk', 'proxy', 'git', '-C', str(repo), *args],
                            capture_output=True, text=True, check=True)
    return result.stdout.strip()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    frozen = OUT / 'input'
    frozen.mkdir(parents=True, exist_ok=True)
    for source in PACKAGE.iterdir():
        if not source.is_file():
            raise RuntimeError('Unexpected non-file package member')
        dest = frozen / source.name
        if dest.exists() and sha(dest) != sha(source):
            raise RuntimeError('Never overwrite changed frozen inputs')
        shutil.copyfile(source, dest)
    ledger = OUT / 'NEXUS_QUICK_CONNECT_LEDGER_R1.json'
    if not ledger.exists():
        shutil.copyfile(frozen / ledger.name, ledger)
    execution = OUT / 'execution'
    execution.mkdir(exist_ok=True)
    repos = {}
    for name, path in (
        ('nexus', ROOT),
        ('connector', ROOT.parent / 'okto-nexus-connector'),
        ('core', ROOT.parent / 'okto-nexus-connector-core'),
    ):
        repos[name] = dict(path=str(path), branch=git(path, 'branch', '--show-current'),
            head=git(path, 'rev-parse', 'HEAD'), status=git(path, 'status', '--porcelain'),
            origin_main=git(path, 'rev-parse', 'origin/main'),
            main_drift=git(path, 'rev-list', '--left-right', '--count', 'HEAD...origin/main'),
            version_file_sha256=sha(path / 'pyproject.toml'))
    record = dict(recorded_at=datetime.now(timezone.utc).isoformat(),
        baseline_before_branch='7f114698e178c415488cd7a112d6ed0cb2ded214',
        analysis_reference='2463c05833f533bc5a5676a5644774cff949ca28',
        analysis_delta=git(ROOT, 'diff', '--shortstat', '2463c05833f533bc5a5676a5644774cff949ca28', 'HEAD'),
        main_fetch='Successfully fetched all three origin/main refs before QC inspection; no merge/reset.',
        repositories=repos,
        inputs={p.name: sha(p) for p in frozen.iterdir() if p.is_file()},
        pins={'connector_core': '0.0.14', 'connector_reference': '0.0.13'},
        inspected_instructions=['User AGENTS -> C:/Users/jpamb/.codex/RTK.md',
            'CONTRIBUTING.md', 'pyproject.toml', '.github/workflows/ci.yml'],
        instructions_note='No AGENTS.md exists in the Nexus checkout; user supplied AGENTS applies.',
        preserved_qualification='UI-R1 global ledger unchanged; native usage UNKNOWN guard retained.',
        effects='Only repo branch/version/documents; no provider, user installation or runtime migration.')
    target = execution / 'qc00-baseline.json'
    if target.exists():
        raise RuntimeError('Baseline already recorded; do not overwrite')
    target.write_text(json.dumps(record, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps(dict(repos={k: dict(branch=v['branch'], head=v['head'], main_drift=v['main_drift'])
                                for k, v in repos.items()}, frozen_files=len(record['inputs']))))


if __name__ == '__main__':
    main()
