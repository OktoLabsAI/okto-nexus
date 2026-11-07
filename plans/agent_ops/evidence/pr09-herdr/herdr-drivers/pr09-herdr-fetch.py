"""Fetch a pinned official Herdr distribution into a new disposable directory."""
import hashlib
import json
from pathlib import Path
import stat
import tempfile
from urllib.request import ProxyHandler, build_opener
import zipfile

url = 'https://github.com/herdrdev/herdr/releases/download/v0.9.5/herdr-windows-x86_64.zip'
expected_sha256 = 'd2c6c9c971c43a0bfdde8c692a9a1a7a45c3e4807cd01ae45662b4734fac1cbf'
root = Path(tempfile.mkdtemp(prefix='pr09-herdr-0.9.5-'))
archive = root / 'herdr-windows-x86_64.zip'
with build_opener(ProxyHandler({})).open(url, timeout=30) as response:
    value = response.read(20 * 1024 * 1024 + 1)
assert len(value) == 10037141, len(value)
actual = hashlib.sha256(value).hexdigest()
assert actual == expected_sha256, actual
archive.write_bytes(value)
distribution = root / 'distribution'
distribution.mkdir()
with zipfile.ZipFile(archive) as package:
    for member in package.infolist():
        target = (distribution / member.filename).resolve()
        assert target.is_relative_to(distribution.resolve()), member.filename
        assert not stat.S_ISLNK(member.external_attr >> 16), member.filename
    package.extractall(distribution)
files = {str(path.relative_to(distribution)).replace('\\', '/'): hashlib.sha256(path.read_bytes()).hexdigest()
         for path in distribution.rglob('*') if path.is_file()}
manifest = dict(version='0.9.5', origin=url, archive_sha256=actual, archive_bytes=len(value),
                root=str(root), distribution=str(distribution), extracted_files=files)
(root / 'distribution-proof.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
print(json.dumps(manifest, indent=2))
