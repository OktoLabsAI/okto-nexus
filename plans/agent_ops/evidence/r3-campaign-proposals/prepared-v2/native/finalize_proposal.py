"""Reuse closed successful checks after isolated-PATH git metadata failure.

No installs, imports, help commands, Task Scheduler calls or service actions.
The initial driver/log are preserved; source-head metadata was read separately.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
original = ROOT / 'prepare_proposal.py'
source = original.read_text(encoding='utf-8')
source = source.replace("for path in (home, state, project):\n    path.mkdir(parents=True, exist_ok=False)",
    "for path in (home, state, project):\n    assert path.is_dir() and not any(path.iterdir())")
start, end = source.index('checks = []'), source.index('installed = json.loads')
source = source[:start] + "checks = json.loads((ROOT / 'read-only-checks.json').read_text())\nassert len(checks) == 8 and all(item['returncode'] == 0 for item in checks)\n" + source[end:]
start, end = source.index('heads = {}'), source.index('proposal = dict')
source = source[:start] + "heads = json.loads((ROOT / 'source-heads.json').read_text())\n" + source[end:]
source = source.replace("write('native-service-campaign-proposal.json', proposal)",
    "proposal['preparation_diagnostic'] = 'Initial driver completed all eight checks and both exact task absence reads, then could not find git in the deliberately scrubbed PATH. This finalizer reused all closed checks and separately collected repository metadata; no native reads or imports were repeated.'\n"
    "write('native-service-campaign-proposal.json', proposal)")
exec(compile(source, str(original), 'exec'))
