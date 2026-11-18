"""Static H09 wiring and actual pinned Connector source proof; no runtime."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / 'security-r9-h02-batch'
REPO = HERE.parents[3]


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new, 1)


for name in ('browser_driver.py', 'fixture_builder.py', 'security_controls.py', 'drift.py', 'playwright-cli.json'):
    shutil.copyfile(BASE / name, HERE / name)
text = once((BASE / 'preflight.py').read_text(), "assert gate['case'] == 'H02'", "assert gate['case'] == 'H09'")
text = once(text, "gate['runtime_mode'] == 'scope_two', 'H02 requires two canonical distinct workspaces'",
            "gate['runtime_mode'] == 'baseline', 'H09 uses existing embedded registered harness context'")
(HERE / 'preflight.py').write_text(text)
text = once((BASE / 'prepare.py').read_text(), "'--mode', 'scope_two', '--browser-window-open',",
            "'--mode', 'baseline', '--browser-window-open',")
(HERE / 'prepare.py').write_text(text)
original = (BASE / 'run.py').read_text()
text = once(original, "r'hst-security-r9-h02-[a-z0-9-]{1,80}'", "r'hst-security-r9-h09-[a-z0-9-]{1,80}'")
start = text.index("        assert gate['case']=='H02'")
end = text.index("        init=(browser/'initialize-template.js').read_text()", start)
replacement = '''        assert gate['case']=='H09' and fixture_ready['mode']=='baseline'
        assert cards[0]['connection']['binding_id']==ref['binding_id']
        cfg.update(card_id=cards[0]['id'],expected_reason='Individual reconnection is not supported by the current canonical API.')
'''
text = text[:start] + replacement + text[end:]
text = once(text, "body('wrong-workspace','h02-wrongtuple.js',cfg)",
            "body('connection-details','h09-connection-details.js',cfg)")
(HERE / 'run.py').write_text(text)
(HERE / 'runner.diff').write_text(''.join(difflib.unified_diff(
    original.splitlines(True), text.splitlines(True), fromfile='qualified H02 supervisor', tofile='H09 disclosure supervisor')))
text = once((BASE / 'curate.py').read_text(), "required={'wrong-workspace'}", "required={'connection-details'}")
text = once(text, "'H02 mutates a GET target workspace; this is not a global-operator workspace ACL test'",
            "'Embedded executor fixture, not live multi-harness Connector daemon; running-daemon clause remains partial'")
text = once(text, "'One wrong-workspace navigation only; other forged tuple dimensions and H03 remain untested'",
            "'Actual pinned Connector CLI scope is static source evidence, not a restart execution'")
(HERE / 'curate.py').write_text(text)
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
wheel = REPO / 'vendor/ci/okto_nexus_connector-0.0.13-py3-none-any.whl'
assert sha(wheel) == '4095484f14110b845b3481941330810f3de1d8fadf9051de0b724cb824177b90'
ready = json.loads((REPO / 'NEXUS_HOME_ESTADOS_R1/execution/package-hst-r9/READY.json').read_text())
site = Path(ready['python']).resolve().parent.parent / 'Lib/site-packages'
members = ('okto_nexus_connector/cli/main.py', 'okto_nexus_connector/cli/commands/reconnect.py',
           'okto_nexus_connector/cli/commands/daemon.py')
with zipfile.ZipFile(wheel) as archive:
    proofs = {}
    for name in members:
        raw = archive.read(name)
        assert (site / name).read_bytes() == raw
        proofs[name] = {'wheel_installed_sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
    parser = archive.read(members[0]).decode('utf-8')
    command = archive.read(members[1]).decode('utf-8')
    assert "sub.add_parser('reconnect', help='gracefully restart the daemon to reconnect all configured connections')" in parser
    assert "scope='all'" in command and 'manager.stop, root' in command and 'manager.start, root' in command
(HERE / 'connector-contract-proof.json').write_text(json.dumps({
    'layer': 'READ_ONLY_ACTUAL_PINNED_WHEEL_AND_INSTALLED_SOURCE', 'wheel_sha256': sha(wheel),
    'members': proofs, 'reconnect_cli_scope': 'all configured connections / whole daemon',
    'command_executed': False, 'individual_capability_exposed': False,
    'live_connector_daemon_preservation_qualified': False}, indent=2) + '\n')
for path in HERE.glob('*.py'):
    ast.parse(path.read_text())
manifest = json.loads((BASE / 'prepared-manifest.json').read_text())
manifest.update(status='H09_STATIC_PREPARED_NOT_EXECUTED', case='H09')
manifest['input_pins'][wheel.relative_to(REPO).as_posix()] = sha(wheel)
for path in HERE.iterdir():
    if path.is_file() and path.name not in ('prepared-manifest.json', 'static-preflight.json'):
        manifest['input_pins'][path.relative_to(REPO).as_posix()] = sha(path)
(HERE / 'prepared-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps({'manifest_sha256': sha(HERE / 'prepared-manifest.json'),
                  'input_pins': len(manifest['input_pins']), 'allocated': False, 'runtime_started': False}))
