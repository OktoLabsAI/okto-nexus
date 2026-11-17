"""Finalize copied evidence only, after normal WSL keeper termination."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
report = json.loads((HERE / 'qualification.json').read_text())
cleanup = json.loads((HERE / 'cleanup.json').read_text())
host = json.loads((HERE / 'cleanup-host.json').read_text())
assert report['passed'] == 202 and report['failed'] == report['skipped'] == 0
assert cleanup['alive'] is False and cleanup['final_state'] == 'absent' and host['absent']
report['cleanup'] = dict(linux=cleanup, windows_keeper=host, signals_used=False,
    evidence_copied_before_stop=True, temporary_runtime_retention='Not guaranteed after WSL idle; Windows evidence retained.')
(HERE / 'qualification.json').write_text(json.dumps(report, indent=2) + '\n')
manifest = {str(p.relative_to(HERE)).replace('\\', '/'):dict(bytes=p.stat().st_size,
    sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in HERE.rglob('*')
    if p.is_file() and p.name != 'manifest.json' and '__pycache__' not in p.parts}
(HERE / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps(dict(qualification_sha256=hashlib.sha256((HERE / 'qualification.json').read_bytes()).hexdigest(),
    manifest_sha256=hashlib.sha256((HERE / 'manifest.json').read_bytes()).hexdigest(), files=len(manifest),
    official_uv_sha256=report['uv_release']['actual_sha256'])))
