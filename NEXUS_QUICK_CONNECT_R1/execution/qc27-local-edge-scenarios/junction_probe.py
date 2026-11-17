"""Bounded owned-path diagnostic, retaining all targets and any created link."""
import json
import os
from pathlib import Path
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
root = Path(tempfile.mkdtemp(prefix='nexus-qc27-junction-diagnostic-')).resolve()
target, link = root / 'target', root / 'link'
target.mkdir()
assert target.resolve().is_relative_to(root) and link.parent.resolve() == root
env = {key: value for key, value in os.environ.items() if key.upper() in ('SYSTEMROOT', 'WINDIR', 'COMSPEC', 'SYSTEMDRIVE', 'PATHEXT')}
env.update(TEMP=str(root), TMP=str(root), HOME=str(root), USERPROFILE=str(root), PATH=str(root))
command = [r'C:/Windows/System32/cmd.exe', '/d', '/c', 'mklink', '/J', str(link), str(target)]
result = subprocess.run(command, cwd=root, env=env, input=b'', capture_output=True, timeout=5)
report = dict(root=str(root), command=command, exit_code=result.returncode,
    stdout=result.stdout.decode('utf-8', errors='replace'), stderr=result.stderr.decode('utf-8', errors='replace'),
    link_exists=link.exists(), is_junction=link.is_junction(),
    target_exists=target.is_dir(), data_removed=False)
(HERE / 'junction-probe.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report))
