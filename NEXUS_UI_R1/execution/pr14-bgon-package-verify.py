from pathlib import Path
import hashlib
import importlib.metadata as metadata
import json
import subprocess
import sys
import zipfile

root = Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
here = Path('C:/Users/jpamb/AppData/Local/Temp/nexus-ui-r1-bgon-package-5wwdklas')
old = Path('C:/Users/jpamb/AppData/Local/Temp/nexus-ui-r1-packages-wry3ter9/nexus-release-bxp/okto_nexus-0.3.5-py3-none-any.whl')
new = here / 'artifacts/okto_nexus-0.3.5-py3-none-any.whl'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

import okto_nexus
import okto_nexus_connector
import nexus_connector_core

origins = {m.__name__: str(Path(m.__file__).resolve())
           for m in (okto_nexus, okto_nexus_connector, nexus_connector_core)}
assert all(Path(value).is_relative_to(here / 'venv') for value in origins.values())
assert sys.flags.isolated == 1
with zipfile.ZipFile(old) as before, zipfile.ZipFile(new) as after:
    python = [name for name in after.namelist() if name.startswith('okto_nexus/') and name.endswith('.py')]
    assert len(python) == 538
    mismatches = [name for name in python if after.read(name) != before.read(name)]
    assert not mismatches, mismatches
    module_payloads = [name for name in after.namelist() if name.startswith('okto_nexus/')
                       and '/http/static/' not in name and not name.endswith('/')]
    assert len(module_payloads) == 708
    assert all(after.read(name) == before.read(name) for name in module_payloads)
    static = [name for name in after.namelist() if '/http/static/' in name and not name.endswith('/')]
    assert not any('index-BXpHvePH.js' in name for name in static)
    payloads = [name for name in after.namelist() if name.startswith('okto_nexus/') and not name.endswith('/')]
    site = Path(okto_nexus.__file__).parent.parent
    assert all((site / name).read_bytes() == after.read(name) for name in payloads)
    assert all((root / 'src' / name).read_bytes() == after.read(name) for name in static)
    changes = [name for name in before.namelist() if name.startswith('okto_nexus/')
               and name in after.namelist() and before.read(name) != after.read(name)]
    removed = sorted(set(before.namelist()) - set(after.namelist()))
    added = sorted(set(after.namelist()) - set(before.namelist()))
smoke = subprocess.run([str(here / 'venv/Scripts/okto-nexus.exe'), '--help'],
                       cwd=here, capture_output=True, text=True, timeout=30)
assert smoke.returncode == 0, smoke.stderr
assert 'connect' in smoke.stdout
candidate = root / 'NEXUS_UI_R1/execution/pr07-native-proposal/candidate-final.json'
assert sha(candidate) == '3ea51229df9bcc4d93d7f42dbe5e4d62a97741d97c99907a49a21cde6fafb88e'
result = {
    'status': 'PASS_PRESENTATION_PACKAGE_DELTA_ONLY',
    'own_prefix': str(here), 'python': sys.version, 'isolated': sys.flags.isolated,
    'origins': origins, 'versions': {name: metadata.version(name) for name in
                                    ('okto-nexus', 'okto-nexus-connector', 'okto-nexus-connector-core')},
    'artifacts': {str(path): sha(path) for path in (new, here / 'artifacts/okto_nexus-0.3.5.tar.gz')},
    'antecedent_bxp_wheel_sha256': sha(old),
    'unchanged_python_files': len(python), 'python_mismatches': mismatches,
    'unchanged_nonstatic_module_payload_files': len(module_payloads),
    'installed_payloads_byte_equal_to_wheel': len(payloads),
    'static_files_byte_equal_to_checkout': len(static),
    'product_changes_vs_bxp': changes, 'zip_members_removed': removed, 'zip_members_added': added,
    'console_help': {'returncode': smoke.returncode, 'connect_present': True},
    'frozen_provider_candidate_unchanged': True,
    'build': {'tool': '2f5a7c', 'exit_code': 0, 'warnings': ['Existing setuptools license table deprecation.']},
    'install': {'tool': '8769bf', 'exit_code': 0, 'packages': 46},
    'twine': {'tool': 'ca1a58', 'exit_code': 0, 'wheel': 'PASSED', 'sdist': 'PASSED'},
    'limits': ['Separate owned prefix; no personal installation/configuration changed.',
               'Package delta verification and console help only; no replacement for all installed tests or browser/AT/native campaign.',
               'BXP provider proposal and installed prefix remain frozen. A later backend change needs a new package delta.',
               'Earlier prose calling708 module payloads Python modules was imprecise:538 are.py,167 are.sql migrations and3 are other module assets. All708 compare equal at this cut.',
               'Initial verifier assertion incorrectly expected708.py files; toolca79e4 failed that oracle before smoke. Corrected count derives from exact wheel member sets, toolbbf4fa.'],
}
out = root / 'NEXUS_UI_R1/execution/pr14-bgon-package-qualification.json'
assert not out.exists()
out.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result, indent=2))
