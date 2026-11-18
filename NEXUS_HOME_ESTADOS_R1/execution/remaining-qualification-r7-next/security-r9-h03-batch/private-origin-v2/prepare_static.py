"""Prepare immutable input-only transform derivative without application imports."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
original = (BASE / 'fixture_transform.py').read_text()
old = "PRIVATE_PROMPT = 'HST_BROWSER_PRIVATE_PROMPT_NOT_FOR_OVERVIEW'\nLABEL = PUBLIC + '\\x1b[31m Bearer ' + PRIVATE_TOKEN"
new = "PRIVATE_PROMPT = 'HST_BROWSER_PRIVATE_PROMPT_NOT_FOR_OVERVIEW' + '\\x1b[31m Bearer ' + PRIVATE_TOKEN\nLABEL = PUBLIC"
assert original.count(old) == 1
effective = original.replace(old, new, 1)
old_proof = "            'canonical_turn_submit_input': True}"
new_proof = "            'canonical_turn_submit_input': True,\n            'public_label_origin': 'hostile HTML only',\n            'private_prompt_origin': ['private marker', 'ESC', 'synthetic Bearer token']}"
assert effective.count(old_proof) == 1
effective = effective.replace(old_proof, new_proof, 1)
ast.parse(effective)
(HERE / 'fixture_transform.py').write_text(effective)
(HERE / 'inputs-only.diff').write_text(''.join(difflib.unified_diff(
    original.splitlines(True), effective.splitlines(True), fromfile='unexecuted H03 mixed-origin draft', tofile='H03 private-origin counterpart')))
for path in HERE.glob('*.py'):
    ast.parse(path.read_text())
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
names = ('run.py', 'prepare.py', 'validate.py', 'fixture_transform.py', 'prepare_static.py', 'inputs-only.diff', 'README.md')
manifest = {'kind': 'H03_PRIVATE_ORIGIN_INPUT_ONLY_PREPARED_NOT_EXECUTED',
            'variant_pins': {name: sha(HERE / name) for name in names},
            'base_pins': {name: sha(BASE / name) for name in (
                'prepared-manifest.json', 'run.py', 'prepare.py', 'fixture_transform.py', 'h03-overview.js')}}
(HERE / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps({'manifest_sha256': sha(HERE / 'manifest.json'),
                  'transform_sha256': sha(HERE / 'fixture_transform.py'),
                  'allocated': False, 'runtime_executed': False}))
