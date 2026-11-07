"""Make the official isolated package visible to passive PATH discovery."""
from pathlib import Path
from dataclasses import asdict
import hashlib
import json
import shutil
import tempfile
import sys

assert sys.flags.isolated
source = Path('C:/Users/jpamb/AppData/Local/Temp/m1-codex-campaign-proposal-ynzvp8yx/artifacts/codex-0.157.0-windows-x64')
root = Path(tempfile.mkdtemp(prefix='m1-native-discovery-'))
target = root / 'codex-0.157.0'
def inventory(folder):
    return {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in folder.rglob('*') if p.is_file()}
before = inventory(source)
assert before['codex-x86_64-pc-windows-msvc.exe'] == 'ed1c7b36e44536809c868864c833af8a857f56599a7a7fe23b908a1ba1093b1f'
shutil.copytree(source, target)
assert inventory(target) == before
shutil.copy2(target / 'codex-x86_64-pc-windows-msvc.exe', target / 'codex.exe')
from nexus_connector_core.discovery import discover_path
candidates = discover_path('codex_app_server', path_env=str(target), trusted_roots=(target,))
assert len(candidates) == 1
selected = candidates[0]
assert Path(selected.executable) == (target / 'codex.exe').resolve()
assert selected.trust == 'selected'
assert inventory(source) == before
after = inventory(target)
assert after == {**before, 'codex.exe': before['codex-x86_64-pc-windows-msvc.exe']}
report = dict(status='PASSIVE_DISCOVERY_PREPARED', source=str(source), package_root=str(target),
    provider_processes_started=0, credentials_read=False, personal_install_changed=False,
    candidate=asdict(selected), source_payload_sha256=before, copied_payload_sha256=after,
    notes=['Official complete package copied byte-for-byte; only an additional codex.exe filename is added.',
           'Discovery uses only this explicit PATH directory and trusted root.',
           'Support/helper execution and real provider/service behavior remain untested.'])
(root / 'discovery.json').write_text(json.dumps(report, indent=2, default=str) + '\n', encoding='utf-8')
print(json.dumps(dict(output=str(root / 'discovery.json'), executable=selected.executable,
    candidate_ref=selected.installation_ref, trust=selected.trust, copied_files=len(after))))
