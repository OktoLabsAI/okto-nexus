"""Prepare own external helper graph; no pytest or product edits."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

HERE = Path(__file__).resolve().parent
OLD = HERE.parent / 'qc12-installed-compatibility'
oldroot = Path(json.loads((OLD / 'allocation.json').read_text())['root'])
root = Path(tempfile.mkdtemp(prefix='nexus-qc14-installed-'))
shutil.copytree(oldroot / 'after', root / 'after', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
for name in ('pytest.ini', 'source-pins.json'):
    shutil.copyfile(oldroot / name, root / name)
draft = Path(r'C:/Users/jpamb/AppData/Local/Temp/nexus-qc14-extra-scenarios-8emg34b9/test_quick_connect_extra_scenarios.py')
target = root / 'after/tests/quick_connect' / draft.name
text = draft.read_text()
text = text.replace("return {table: sorted([tuple(row) for row in uow.connection.execute('SELECT * FROM ' + table)], key=repr)\n                for table in TABLES}",
    "return {table: sorted([{key: row[key] for key in row.keys() if not (table == 'agents' and key == 'last_seen_at')}\n                              for row in uow.connection.execute('SELECT * FROM ' + table)], key=repr)\n                for table in TABLES}")
text = text.replace("assert result['state'] in ('refused', 'unconfirmed') and result.get('code')",
                    "assert result['state'] in ('refused', 'unconfirmed')\n    assert result['code'] == 'HARNESS_ID_ALREADY_EXISTS'")
assert text != draft.read_text()
target.write_text(text, encoding='utf-8')
(HERE / 'allocation.json').write_text(json.dumps(dict(root=str(root), draft_original=str(draft),
    original_sha256=hashlib.sha256(draft.read_bytes()).hexdigest(), derivative=str(target),
    derivative_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
    changes=['Exclude only agents.last_seen_at telemetry from identity snapshot.',
             'Require exact HARNESS_ID_ALREADY_EXISTS for bound-winner race.'],
    executed=False), indent=2) + '\n')
shutil.copyfile(OLD / 'package-ready.json', HERE / 'package-ready.json')
src = (OLD / 'run.py').read_text()
start = src.index('nodes=[')
end = src.index('\nfor label,node in nodes:', start)
functions = ['test_e03_second_same_harness_add_without_id_proposes_codex_2',
    'test_h06_explicit_add_plan_preserves_public_namespace_and_project_drafts[False]',
    'test_h06_explicit_add_plan_preserves_public_namespace_and_project_drafts[True]',
    'test_g13_expired_canonical_grants_are_not_renewed_by_resume',
    'test_f17_free_id_review_loses_race_before_new_test_identity_or_grant']
nodes = [(str(i + 1) + '-' + f.split('_')[1], 'tests/quick_connect/' + draft.name + '::' + f)
         for i, f in enumerate(functions)]
src = src[:start] + 'nodes=' + repr(nodes) + src[end:]
src = src.replace('stdin=subprocess.DEVNULL', 'stdin=subprocess.PIPE')
src = src.replace('known[process.pid]=Owned(process.pid)',
                  'process.stdin.close()\n        known[process.pid]=Owned(process.pid)')
src = src.replace("HERE.parent/'qc08-package/package.py'", "HERE.parent/'qc11-package/package.py'")
src = src.replace("before=payload()", "before=payload()\n(root/'payload-start.json').write_text(json.dumps(before,indent=2)+'\\n')")
src = src.replace("after=payload()", "after=payload()\n(root/'payload-end.json').write_text(json.dumps(after,indent=2)+'\\n')")
needle = "@pytest.hookimpl(hookwrapper=True)"
finish = """def pytest_sessionfinish(session,exitstatus):
    bad={name:getattr(module,'__file__',None) for name,module in sys.modules.items()
         if name.split('.')[0] in ('okto_nexus','nexus_connector_core','okto_nexus_connector')
         and getattr(module,'__file__',None) and not pathlib.Path(module.__file__).resolve().is_relative_to(PREFIX)}
    (OUT/'origins-finish.json').write_text(json.dumps(dict(exitstatus=exitstatus,bad=bad,prefix=sys.prefix),indent=2))
    assert not bad,bad

"""
assert needle in src
src = src.replace(needle, finish + needle)
(HERE / 'run.py').write_text(src, encoding='utf-8')
print(json.dumps(dict(root=str(root), external_test=str(target),
                     sha256=hashlib.sha256(target.read_bytes()).hexdigest())))
