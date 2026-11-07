"""Download official immutable-release bytes only. Never execute a native binary."""
from pathlib import Path, PurePosixPath
import hashlib
import json
import time
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / 'public'
ARTIFACTS = ROOT / 'artifacts'
API = 'https://api.github.com/repos/openai/codex/releases/tags/rust-v0.157.0'
EXPECTED = 'sha256:df63d86e72bc1a27f13899ad0467c4b312d8ee2cb67ae3a09e37f734d9f0edcb'

def fetch(url, target, cap):
    started = time.monotonic()
    request = urllib.request.Request(url, headers={'User-Agent': 'okto-m1-readonly-artifact-qualification', 'Accept': 'application/vnd.github+json'})
    size = 0
    digest = hashlib.sha256()
    with urllib.request.urlopen(request, timeout=30) as response, target.open('xb') as out:
        while chunk := response.read(1024 * 1024):
            size += len(chunk)
            if size > cap or time.monotonic() - started > 180:
                raise ValueError('bounded artifact download exceeded its limit')
            out.write(chunk)
            digest.update(chunk)
    return {'size': size, 'sha256': digest.hexdigest()}

def main():
    metadata_path = ARTIFACTS / 'github-release-metadata.json'
    metadata_digest = fetch(API, metadata_path, 2 * 1024 * 1024)
    data = json.loads(metadata_path.read_bytes())
    if data['tag_name'] != 'rust-v0.157.0' or data['draft'] or data['prerelease']:
        raise ValueError('unexpected release metadata')
    selected = [x for x in data['assets'] if x['name'] == 'codex-x86_64-pc-windows-msvc.zip']
    if len(selected) != 1:
        raise ValueError('exact Windows asset absent or ambiguous')
    asset = selected[0]
    url = asset['browser_download_url']
    if url != 'https://github.com/openai/codex/releases/download/rust-v0.157.0/codex-x86_64-pc-windows-msvc.zip':
        raise ValueError('unexpected official asset URL')
    archive = ARTIFACTS / asset['name']
    download = fetch(url, archive, 256 * 1024 * 1024)
    if download['size'] != asset['size']:
        raise ValueError('asset size mismatch')
    if asset.get('digest') and asset['digest'] != 'sha256:' + download['sha256']:
        raise ValueError('official asset digest mismatch')
    extracted = ARTIFACTS / 'codex-0.157.0-windows-x64'
    extracted.mkdir()
    inventory = []
    with zipfile.ZipFile(archive) as bundle:
        entries = bundle.infolist()
        if len(entries) > 30 or sum(x.file_size for x in entries) > 512 * 1024 * 1024:
            raise ValueError('archive bounds exceeded')
        for member in entries:
            name = PurePosixPath(member.filename)
            if name.is_absolute() or '..' in name.parts or ':' in member.filename or '\\' in member.filename:
                raise ValueError('archive path escapes scope')
            if member.is_dir():
                continue
            target = extracted.joinpath(*name.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            payload = bundle.read(member)
            target.write_bytes(payload)
            inventory.append({'path': name.as_posix(), 'size': len(payload), 'sha256': hashlib.sha256(payload).hexdigest()})
    executables = [x for x in inventory if PurePosixPath(x['path']).name == 'codex.exe']
    if len(executables) != 1:
        raise ValueError('exact native executable missing or ambiguous')
    executable = executables[0]
    identity = {'algorithm': 'core.build_identity.v3', 'kind': 'executable', 'sha256': executable['sha256'], 'size': executable['size']}
    raw = json.dumps(identity, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
    build_identity = 'sha256:' + hashlib.sha256(raw).hexdigest()
    proof = {
        'format': 'okto.m1.codex-artifact-preparation', 'revision': 1,
        'source_url': data['html_url'], 'metadata_url': API, 'metadata_digest': metadata_digest,
        'release_id': data['id'], 'tag_name': data['tag_name'], 'published_at': data['published_at'],
        'asset': {k: asset.get(k) for k in ('id', 'name', 'size', 'digest', 'browser_download_url', 'updated_at')},
        'download': download, 'inventory': inventory,
        'native_executable': str(extracted / executable['path']),
        'build_identity': build_identity, 'expected_qualified_build_identity': EXPECTED,
        'qualified_bytes_equal': build_identity == EXPECTED,
        'native_executions': 0, 'postinstall_scripts_executed': 0,
        'personal_installation_changed': False, 'personal_authentication_read': False,
        'qualification_scope': 'Byte identity only; no live handshake, inference, provider login, local binding or M1 acceptance is claimed.',
    }
    (PUBLIC / 'codex-0.157.0-artifact-proof.json').write_text(json.dumps(proof, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'qualified_bytes_equal': proof['qualified_bytes_equal'], 'build_identity': build_identity, 'proof': str(PUBLIC / 'codex-0.157.0-artifact-proof.json')}))
    if build_identity != EXPECTED:
        raise SystemExit(2)

if __name__ == '__main__':
    main()
