"""Static H02 wiring from qualified supervisors; never allocates or starts apps."""
import ast
import hashlib
import json
from pathlib import Path
import shutil
import difflib

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / 'security-r9-s2-batch'


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new, 1)


for name in ('browser_driver.py', 'fixture_builder.py', 'security_controls.py', 'drift.py', 'playwright-cli.json'):
    shutil.copyfile(BASE / name, HERE / name)
shutil.copyfile(HERE.parent / 'security-adversarial-r9-prepared/h02-wrongtuple.js', HERE / 'h02-wrongtuple.js')
text = (BASE / 'preflight.py').read_text()
text = once(text, "assert gate['case'] == 'S2' and gate['deadline_seconds'] == 180",
            "assert gate['case'] == 'H02' and gate['deadline_seconds'] == 180")
text = once(text, "gate['runtime_mode'] == 'baseline', 'S2 baseline has no live question'",
            "gate['runtime_mode'] == 'scope_two', 'H02 requires two canonical distinct workspaces'")
text = once(text, "assert gate.get('allow_exact_observation_inserts', False) is (gate['case'] == 'S2')",
            "assert gate.get('allow_exact_observation_inserts', False) is False")
(HERE / 'preflight.py').write_text(text)
text = (BASE / 'prepare.py').read_text()
text = once(text, "'--mode', 'baseline', '--browser-window-open',", "'--mode', 'scope_two', '--browser-window-open',")
text = once(text, "    ], checked['case'])", "    ], 'S1')")
(HERE / 'prepare.py').write_text(text)
original = (BASE / 'reader-v2/effective-run.py.txt').read_text()
text = once(original, "r'hst-security-r9-s2-[a-z0-9-]{1,80}'", "r'hst-security-r9-h02-[a-z0-9-]{1,80}'")
start = text.index("        if gate['case']=='S1':")
end = text.index('    except BaseException as error:', start)
replacement = '''        assert gate['case']=='H02' and fixture_ready['mode']=='scope_two'
        references=fixture_ready['references']
        assert len(references)==2 and len({r['workspace_id'] for r in references})==2
        assert cards[0]['connection']['binding_id']==ref['binding_id']
        events=[e for e in cards[0]['events_preview']
                if e['kind']=='result' and e.get('target') and e.get('result')
                and e['result'].get('preview')]
        assert len(events)==1, 'Require unique canonical result event, never latest/fallback'
        event=events[0]
        cfg.update(target=event['target'],event_id=event['id'],button_name='View delivery',
            changes={},wrong_workspace=references[1]['workspace_id'],expected_status=409,
            protected_marker=event['result']['preview'])
        init=(browser/'initialize-template.js').read_text()
        assert init.count('__CONFIG__')==1
        temporary=root/'initialize.js'
        temporary.write_text(init.replace('__CONFIG__',json.dumps({'url':url,'workspace_id':ref['workspace_id']})))
        cli('initialize','run-code','--filename='+str(temporary))
        control('security-snapshot-before-get')
        body('wrong-workspace','h02-wrongtuple.js',cfg)
        control('security-snapshot-after-get')
        compare('before-get','after-get')
'''
text = text[:start] + replacement + text[end:]
(HERE / 'run.py').write_text(text)
(HERE / 'runner.diff').write_text(''.join(difflib.unified_diff(
    original.splitlines(True), text.splitlines(True), fromfile='qualified reader-v2 effective supervisor', tofile='H02 only supervisor')))
text = (BASE / 'curate.py').read_text()
text = once(text, "required={'passive','control-before','control-after'} if data['case']=='S1' else {'idle','completion'}",
            "required={'wrong-workspace'}")
text = once(text, "'S2 baseline has no occupied handoff claim/one-shot slot; H08 active-work clause remains partial'",
            "'H02 mutates a GET target workspace; this is not a global-operator workspace ACL test'")
text = once(text, "'S2 reported completion is not canonical task completion or verified native success'",
            "'One wrong-workspace navigation only; other forged tuple dimensions and H03 remain untested'")
(HERE / 'curate.py').write_text(text)
for path in HERE.glob('*.py'):
    ast.parse(path.read_text())
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
manifest = json.loads((BASE / 'prepared-manifest.json').read_text())
manifest.update(status='H02_STATIC_PREPARED_NOT_EXECUTED', case='H02')
repo = HERE.parents[3]
for path in HERE.iterdir():
    if path.is_file() and path.name not in ('prepared-manifest.json', 'static-preflight.json'):
        manifest['input_pins'][path.relative_to(repo).as_posix()] = sha(path)
(HERE / 'prepared-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps({'manifest_sha256': sha(HERE / 'prepared-manifest.json'),
                  'input_pins': len(manifest['input_pins']), 'allocated': False, 'runtime_started': False}))
