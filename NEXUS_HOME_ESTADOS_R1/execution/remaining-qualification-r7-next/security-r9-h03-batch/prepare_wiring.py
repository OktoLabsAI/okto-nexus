"""Static H03 derivation from the qualified H02 supervisor; no runtime."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / 'security-r9-h02-batch'


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new, 1)


for name in ('browser_driver.py', 'fixture_builder.py', 'security_controls.py', 'drift.py', 'playwright-cli.json'):
    shutil.copyfile(BASE / name, HERE / name)
text = (BASE / 'preflight.py').read_text()
text = once(text, "assert gate['case'] == 'H02'", "assert gate['case'] == 'H03'")
text = once(text, "gate['runtime_mode'] == 'scope_two', 'H02 requires two canonical distinct workspaces'",
            "gate['runtime_mode'] == 'baseline', 'H03 uses one canonical registered binding'")
(HERE / 'preflight.py').write_text(text)
text = (BASE / 'prepare.py').read_text()
text = once(text, "'--mode', 'scope_two', '--browser-window-open',", "'--mode', 'baseline', '--browser-window-open',")
anchor = "    runtime_ready = root / 'runtime-ready.json'"
text = once(text, anchor, "    transform = module('h03_fixture_transform', HERE / 'fixture_transform.py')\n"
            "    changed = transform.transform(root, root / 'fixture.py', proof['fixture_sha256'])\n"
            "    proof.update(changed)\n" + anchor)
(HERE / 'prepare.py').write_text(text)
original = (BASE / 'run.py').read_text()
text = once(original, "r'hst-security-r9-h02-[a-z0-9-]{1,80}'", "r'hst-security-r9-h03-[a-z0-9-]{1,80}'")
start = text.index("        assert gate['case']=='H02'")
end = text.index("        init=(browser/'initialize-template.js').read_text()", start)
replacement = '''        assert gate['case']=='H03' and fixture_ready['mode']=='baseline'
        admission=json.loads((root/'control/h03-label-admission.json').read_text())
        assert admission['review_accepted'] is True, 'Canonical label not admitted; no hostile DOM claim'
        assert list((root/'control').glob('h03-prompt-issued-*.json')), 'Canonical private prompt not submitted'
        cfg.update(private_token='HST_BROWSER_PRIVATE_TOKEN',private_prompt='HST_BROWSER_PRIVATE_PROMPT_NOT_FOR_OVERVIEW')
'''
text = text[:start] + replacement + text[end:]
text = once(text, "body('wrong-workspace','h02-wrongtuple.js',cfg)", "body('hostile-overview','h03-overview.js',cfg)")
(HERE / 'run.py').write_text(text)
(HERE / 'runner.diff').write_text(''.join(difflib.unified_diff(
    original.splitlines(True), text.splitlines(True), fromfile='qualified H02 supervisor', tofile='H03 overview supervisor')))
text = (BASE / 'curate.py').read_text()
text = once(text, "required={'wrong-workspace'}", "required={'hostile-overview'}")
text = once(text, "'H02 mutates a GET target workspace; this is not a global-operator workspace ACL test'",
            "'H03 overview only; authorized transcript, hostile artifacts and filenames not exercised'")
text = once(text, "'One wrong-workspace navigation only; other forged tuple dimensions and H03 remain untested'",
            "'JSON control escaping and static browser text are distinct; parsed ESC removal is not required'")
text = once(text, "    (output/'qualification.json').write_text(json.dumps(report,indent=2)+'\\n')",
            "    admission=root/'control/h03-label-admission.json'\n"
            "    report['canonical_label_admission']=json.loads(admission.read_text()) if admission.exists() else None\n"
            "    report['ansi_observations']=[phase['result'].get('ansi_observations') for phase in data['results']]\n"
            "    (output/'qualification.json').write_text(json.dumps(report,indent=2)+'\\n')")
(HERE / 'curate.py').write_text(text)
for path in HERE.glob('*.py'):
    ast.parse(path.read_text())
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
manifest = json.loads((BASE / 'prepared-manifest.json').read_text())
manifest.update(status='H03_STATIC_PREPARED_NOT_EXECUTED', case='H03')
repo = HERE.parents[3]
for path in HERE.iterdir():
    if path.is_file() and path.name not in ('prepared-manifest.json', 'static-preflight.json'):
        manifest['input_pins'][path.relative_to(repo).as_posix()] = sha(path)
(HERE / 'prepared-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps({'manifest_sha256': sha(HERE / 'prepared-manifest.json'),
                  'input_pins': len(manifest['input_pins']), 'allocated': False, 'runtime_started': False}))
