from pathlib import Path
import hashlib
import json
import shutil

root = Path(__file__).resolve().parent
repo = Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
destination = root / 'installed-fixtures'
for rel in ('tests', 'tests/execution_r4'):
    (destination / rel).mkdir(parents=True, exist_ok=True)
    for source in (repo / rel).glob('*.py'):
        shutil.copyfile(source, destination / rel / source.name)
manifest = {p.relative_to(destination).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(destination.rglob('*.py'))}
(root / 'installed-fixture-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
runner = (root / 'installed_nexus_runner.py').read_text(encoding='utf-8')
runner = runner.replace("repo = Path('D:/Projetos/Techridy/okto_labs_okto_nexus')", "repo = root / 'installed-fixtures'")
runner = runner.replace('installed-nexus-final.xml', 'installed-nexus-final-v2.xml').replace('installed-nexus-origins.json', 'installed-nexus-origins-v2.json')
(root / 'installed_nexus_runner_v2.py').write_text(runner, encoding='utf-8')
launcher = (root / 'launch_installed_tests.py').read_text(encoding='utf-8')
launcher = launcher.replace('installed_nexus_runner.py', 'installed_nexus_runner_v2.py').replace('installed-nexus.stdout.txt', 'installed-nexus-v2.stdout.txt').replace('installed-nexus.stderr.txt', 'installed-nexus-v2.stderr.txt')
(root / 'launch_installed_tests_v2.py').write_text(launcher, encoding='utf-8')
print(json.dumps({'fixture_files': len(manifest), 'products_copied': False}))
