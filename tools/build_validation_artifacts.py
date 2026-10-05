"""Build wheel/sdist from an isolated copy and a fresh dashboard compilation."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix='nexus-validation-source-') as directory:
        source = Path(directory)
        shutil.copytree(root / 'src', source / 'src', ignore=shutil.ignore_patterns(
            '__pycache__', '*.pyc', '*.egg-info', 'static'))
        for name in ('pyproject.toml', 'README.md', 'LICENSE'):
            shutil.copy2(root / name, source / name)
        assets = source / 'src/okto_nexus/adapters/inbound/http/static'
        with (output / 'build.log').open('w', encoding='utf-8') as log:
            for command, cwd in (
                (['rtk', 'proxy', 'node', 'node_modules/typescript/bin/tsc', '-b'], root / 'frontend'),
                (['rtk', 'proxy', 'node', 'node_modules/vite/bin/vite.js', 'build',
                  '--outDir', str(assets), '--emptyOutDir', 'false'], root / 'frontend'),
                (['rtk', 'proxy', 'uv', 'build', '--out-dir', str(output), str(source)], root),
            ):
                subprocess.run(command, cwd=cwd, stdout=log, stderr=subprocess.STDOUT, check=True)
        artifacts = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in output.iterdir() if p.suffix in ('.whl', '.gz')}
        report = dict(head=subprocess.check_output(['rtk', 'proxy', 'git', 'rev-parse', 'HEAD'],
                                                   cwd=root, text=True).strip(),
                      artifacts=artifacts, source_sha256={
                          p.relative_to(source).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in sorted(source.rglob('*')) if p.is_file() and
                          ('src' in p.parts or p.name in ('pyproject.toml', 'README.md', 'LICENSE'))},
                      scope='Development validation build; source hashes include reviewed uncommitted changes, not a final freeze')
        (output / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(artifacts, indent=2))


if __name__ == '__main__':
    main()
