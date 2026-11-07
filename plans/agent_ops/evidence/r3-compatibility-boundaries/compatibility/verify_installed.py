"""Prove module origin and raw installed package bytes for one pinned stack."""
from pathlib import Path
import hashlib
import importlib
import importlib.metadata
import json
import sys
import zipfile

spec = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
result = {}
for item in spec['artifacts']:
    wheel = Path(item['wheel'])
    assert hashlib.sha256(wheel.read_bytes()).hexdigest() == item['sha256']
    module = importlib.import_module(item['module'])
    package = Path(module.__file__).resolve().parent
    assert 'site-packages' in package.parts
    assert package.is_relative_to(Path(spec['expected_package_root']))
    matched = {}
    with zipfile.ZipFile(wheel) as z:
        for name in z.namelist():
            if not name.startswith(item['module'] + '/') or name.endswith('/'):
                continue
            relative = name.split('/', 1)[1]
            raw = z.read(name)
            assert (package / relative).read_bytes() == raw, relative
            if item.get('source'):
                assert (Path(item['source']) / name).read_bytes() == raw, relative
            matched[relative] = hashlib.sha256(raw).hexdigest()
    result[item['module']] = {'package_path': str(package), 'wheel_sha256': item['sha256'],
                              'matched_file_count': len(matched), 'files': matched}
result['dependency_versions'] = {name: importlib.metadata.version(name) for name in
                                ('mcp', 'httpx', 'fastapi', 'uvicorn', 'pydantic', 'websockets')}
Path(spec['output']).write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
