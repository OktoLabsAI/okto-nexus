"""Prepare exact reader-only diff without loading product or starting processes."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
original = (BASE / 'run.py').read_text()
old = """            if path.exists() and name in json.loads(path.read_text()).get('done',[]):
                return
"""
new = """            invalid_read = None
            try:
                raw = path.read_bytes()
            except FileNotFoundError:
                invalid_read = {'kind': 'missing', 'bytes': None, 'sha256': None}
            else:
                try:
                    observed = json.loads(raw)
                except json.JSONDecodeError:
                    invalid_read = {'kind': 'invalid_json', 'bytes': len(raw),
                                    'sha256': hashlib.sha256(raw).hexdigest()}
                else:
                    if name in observed.get('done', []):
                        return
            if invalid_read is not None:
                audit = root / 'security-control-invalid-reads.jsonl'
                with audit.open('a', encoding='utf-8') as stream:
                    stream.write(json.dumps({'marker': name,
                        'ordinal': control_invalid_reads[0] + 1,
                        **invalid_read}) + '\\n')
                control_invalid_reads[0] += 1
"""
assert original.count(old) == 1
anchor = '    def control(name):\n'
assert original.count(anchor) == 1
effective = original.replace(anchor, '    control_invalid_reads = [0]\n\n' + anchor, 1).replace(old, new, 1)
ast.parse(effective)
ast.parse((HERE / 'run.py').read_text())
assert effective.count('marker.touch()') == original.count('marker.touch()') == 1
assert effective.count('security-obs-idle') == original.count('security-obs-idle')
assert effective.count('security-obs-completion') == original.count('security-obs-completion')
assert 'end = min(deadline,time.monotonic()+20)' in effective
(HERE / 'effective-run.py.txt').write_text(effective)
(HERE / 'reader-only.diff').write_text(''.join(difflib.unified_diff(
    original.splitlines(True), effective.splitlines(True), fromfile='frozen S2/run.py', tofile='S2 reader counterpart')))
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
manifest = {'kind': 'S2_CONTROL_READER_ONLY_PREPARED_NOT_EXECUTED',
            'base_manifest_sha256': sha(BASE / 'prepared-manifest.json'),
            'base_driver_sha256': sha(BASE / 'run.py'),
            'variant_pins': {name: sha(HERE / name) for name in (
                'run.py', 'prepare_static.py', 'effective-run.py.txt', 'reader-only.diff', 'README.md')}}
(HERE / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps({'manifest_sha256': sha(HERE / 'manifest.json'),
                  'effective_driver_sha256': sha(HERE / 'effective-run.py.txt'),
                  'allocated': False, 'application_imported': False}))
