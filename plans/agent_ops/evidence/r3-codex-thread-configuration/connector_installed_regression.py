from pathlib import Path
import hashlib
import importlib
import json
import sys

root = Path(__file__).parent
source = root / 'connector-tests'
out = root / 'connector-qualification'
assert sys.flags.isolated
sys.path.insert(0, str(source / 'tests'))
sys.path.insert(0, str(source))
modules = [importlib.import_module(name) for name in
           ('okto_nexus', 'okto_nexus_connector', 'nexus_connector_core')]
assert all(Path(module.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()) for module in modules)
files = [p for p in source.rglob('*') if p.is_file() and '__pycache__' not in p.parts and '.pytest_cache' not in p.parts]
files += [p for module in modules for p in Path(module.__file__).parent.rglob('*')
          if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc']

def hashes():
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}

before = hashes()
(out / 'input-hashes-before.json').write_text(json.dumps(before, indent=2)+'\n')
import pytest
code = pytest.main(['-q', '-c', str(source / 'pytest.ini'), '--confcutdir', str(source / 'tests'),
                   str(source / 'tests/unit/test_r4_events.py'),
                   str(source / 'tests/unit/test_r4_event_recovery.py'),
                   '--basetemp', str(out / 'test-state'), '--junitxml', str(out / 'results.xml')])
after = hashes()
(out / 'input-hashes-after.json').write_text(json.dumps(after, indent=2)+'\n')
shadowed = [name for name, module in tuple(sys.modules.items())
            if name.split('.')[0] in {m.__name__ for m in modules}
            and getattr(module, '__file__', None)
            and not Path(module.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())]
(out / 'status.json').write_text(json.dumps(dict(exit_code=int(code), inputs_unchanged=before == after,
                                                input_count=len(before), product_shadows=shadowed), indent=2)+'\n')
assert before == after and not shadowed
raise SystemExit(code)
