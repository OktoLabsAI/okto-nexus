"""Finite isolated v9 preparation only, never product integration or campaign."""
import ast
import hashlib
import json
from pathlib import Path
import runpy
import sys
import types
import zipfile

ROOT = Path(__file__).parent
WHEEL = Path('C:/Users/jpamb/AppData/Local/Temp/m1-check-recovery-inopit5p/wheels/okto_nexus-0.3.3-py3-none-any.whl')
assert hashlib.sha256(WHEEL.read_bytes()).hexdigest() == '99e1d530b27aeba7dcbd8adae8772ac19eaf4354ad5c31fdb80c0ed6e63d7680'
assert Path(sys.prefix) == ROOT / 'installation/venv'
sys.path[:0] = [str(ROOT), str(ROOT / 'controller')]
# The controller catches only this error type. Extract its exact class AST
# from the candidate wheel; no application package or native module imported.
with zipfile.ZipFile(WHEEL) as archive:
    source = archive.read('okto_nexus/application/terminal_connection.py').decode()
node = [n for n in ast.parse(source).body if isinstance(n, ast.ClassDef) and n.name == 'ConnectionError']
assert len(node) == 1 and not node[0].decorator_list
module = types.ModuleType('okto_nexus.application.terminal_connection')
exec(compile(ast.Module(body=node, type_ignores=[]), '<exact-wheel-ConnectionError-only>', 'exec'), module.__dict__)
sys.modules[module.__name__] = module
proof = {'dependency':'ConnectionError class AST only',
         'source_sha256':hashlib.sha256(source.encode()).hexdigest(),
         'class_sha256':hashlib.sha256(ast.get_source_segment(source,node[0]).encode()).hexdigest(),
         'limits':'No installed Nexus import or integration is represented by these tests.'}
(ROOT / 'class-only-dependency.json').write_text(json.dumps(proof,indent=2)+'\n',encoding='utf-8')
sys.argv = [str(ROOT / 'test_entry_guards.py')]
runpy.run_path(str(ROOT / 'test_entry_guards.py'), run_name='__main__')
import pytest
raise SystemExit(pytest.main([
    str(ROOT / 'controller/test_v9.py'), str(ROOT / 'installation/test_timed_install.py'),
    '-q', '-p', 'no:cacheprovider', '--basetemp', str(ROOT / 'synthetic-test-homes'),
    '--junitxml', str(ROOT / 'pure-tests.xml'),
]))
