"""Activate the qualified environment's standard dependency .pth files."""
from pathlib import Path
import json

root = Path(__file__).resolve().parent
pth = root / 'old-venv/Lib/site-packages/qualified-dependencies.pth'
(root / 'dependency-path-second-attempt.txt').write_bytes(pth.read_bytes())
dependency = 'C:/Users/jpamb/AppData/Local/Temp/nexus-ci-connector-refresh-la1tb1l6/venv/Lib/site-packages'
pth.write_text('import site; site.addsitedir(' + repr(dependency) + ')\n', encoding='utf-8')
(root / 'runtime-dependencies-final.json').write_text(json.dumps({
    'readonly_runtime_dependency_path': dependency,
    'bootstrap': 'site.addsitedir activates the existing qualified pywin32 .pth paths',
    'build_only_dependency_path': 'C:/Users/jpamb/AppData/Roaming/Python/Python313/site-packages',
    'build_only_path_removed_before_runtime': True,
    'shared_environment_mutations': False,
    'attempts': [
        {'directory': 'matrix', 'outcome': 'preparation failure before any listener/request',
         'reason': 'Plain sys.path fallback omitted standard pywin32 .pth bootstrap'},
        {'directory': 'matrix-final', 'outcome': 'preparation failure before any listener/request',
         'reason': 'Preparation one-liner accidentally rewrote the dependency expression three times'},
    ],
}, indent=2) + '\n', encoding='utf-8')
