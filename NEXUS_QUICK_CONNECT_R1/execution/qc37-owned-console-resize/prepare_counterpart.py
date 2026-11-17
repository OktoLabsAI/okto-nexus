import hashlib
import json
from pathlib import Path
import shutil
import tempfile

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
prior = Path(json.loads((HERE / 'allocation.json').read_text())['root'])
root = Path(tempfile.mkdtemp(prefix='nexus-qc37-used-console-')).resolve()
shutil.copytree(prior / 'fixtures', root / 'fixtures', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
for name in ['child.py', 'win.py', 'pytest.ini']:
    shutil.copyfile(prior / name, root / name)
for name in ['cwd', 'empty-path']:
    (root / name).mkdir()
text = (prior / 'controller.py').read_text()
old = '''        count = value.size.X * value.size.Y
        assert 0 < count <= 1000000
        buffer, read = ctypes.create_unicode_buffer(count), w.DWORD()
        assert kernel.ReadConsoleOutputCharacterW(output_fd, buffer, count, Coord(0, 0), ctypes.byref(read))'''
new = '''        start_y = max(0, value.cursor.Y - 399)
        used_lines = value.cursor.Y - start_y + 1
        count = value.size.X * used_lines
        metadata = dict(label=label, buffer_width=value.size.X, buffer_height=value.size.Y,
            cursor_x=value.cursor.X, cursor_y=value.cursor.Y, start_y=start_y,
            lines=used_lines, chars=count, window=[value.window.Left, value.window.Top, value.window.Right, value.window.Bottom])
        with (ROOT / 'console-read-metadata.jsonl').open('a') as stream:
            stream.write(json.dumps(metadata) + '\\n')
        assert 0 < value.size.X <= 500 and 0 < used_lines <= 400 and 0 < count <= 200000
        buffer, read = ctypes.create_unicode_buffer(count), w.DWORD()
        assert kernel.ReadConsoleOutputCharacterW(output_fd, buffer, count, Coord(0, start_y), ctypes.byref(read))'''
assert old in text
text = text.replace(old, new)
old = '''        assert after.size.X == columns and after.window.Right - after.window.Left + 1 == columns'''
# Original controller has no serialized resize dimensions; record them before validating.
text = text.replace("        assert after.size.X == columns and after.window.Right - after.window.Left + 1 == columns", "        assert after.size.X == columns and after.window.Right - after.window.Left + 1 == columns")
# Preserve any existing resize proof emitted by the original exact source.
(root / 'controller.py').write_text(text)
pins = {p.relative_to(REPO).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in (REPO / 'src').rglob('*') if p.is_file() and '__pycache__' not in p.parts}
test = REPO / 'tests/quick_connect/test_quick_connect_pty.py'
pins[test.relative_to(REPO).as_posix()] = hashlib.sha256(test.read_bytes()).hexdigest()
(root / 'source-pins.json').write_text(json.dumps(pins, indent=2))
(HERE / 'counterpart-allocation.json').write_text(json.dumps({'root': str(root)}, indent=2))
runner = (HERE / 'run.py').read_text().replace("HERE / 'allocation.json'", "HERE / 'counterpart-allocation.json'")
(HERE / 'run_counterpart.py').write_text(runner)
print(json.dumps({'root': str(root), 'prepared_only': True}))
