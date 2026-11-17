"""Delta only: keep initial proposal/six results immutable, qualify variable metadata."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile

HERE=Path(__file__).resolve().parent
PARENT=HERE.parent
REPO=HERE.parents[3]
root=Path(tempfile.mkdtemp(prefix='nexus-qc35v2-derived-')).resolve()
previous=Path('C:/Users/jpamb/AppData/Local/Temp/nexus-qc35-derived-c_7iftic')
shutil.copytree(previous/'after',root/'after',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
shutil.copyfile(previous/'pytest.ini',root/'pytest.ini')
text=(PARENT/'test_review_cancel.py').read_text()
text=text.replace('from copy import deepcopy\n','from copy import deepcopy\nimport pytest\n')
text=text.replace('def test_c02_g08_new_unmapped_cwd_basename_review_cancel_emits_honest_final_state(quick_cli,monkeypatch,capsys):',
    "@pytest.mark.parametrize('mode',['quick','legacy'])\ndef test_c02_g08_new_unmapped_cwd_basename_review_cancel_emits_honest_final_state(quick_cli,monkeypatch,capsys,mode):")
text=text.replace("    monkeypatch.setattr(git_project_hint,'_trusted_git',c.trusted_git)",
    "    def no_git(*args,**kwargs):\n        pytest.fail('Legacy explicit selectors must not discover Git')\n    monkeypatch.setattr(git_project_hint,'_trusted_git',c.trusted_git if mode=='quick' else no_git)")
text=text.replace("        assert saved['selection']['quick_connect']['project_name_source']=='directory'\n        assert saved['selection']['quick_connect']['name_discovery']['status']=='fallback'",
    "        if mode=='quick':\n            assert saved['selection']['quick_connect']['project_name_source']=='directory'\n            assert saved['selection']['quick_connect']['name_discovery']['status']=='fallback'\n        else:\n            assert 'quick_connect' not in saved['selection']\n            assert saved['selection']['client']=='codex'\n            assert 'public_connection' not in saved['request']")
text=text.replace("        assert 'Project name source: directory' in captured.out",
    "        if mode=='quick':\n            assert 'Project name source: directory' in captured.out\n            assert 'ID do Harness (proposed): codex' in captured.out\n        else:\n            assert 'Project name source:' not in captured.out\n            assert 'ID do Harness (proposed):' not in captured.out")
text=text.replace("        assert 'ID do Harness (proposed): codex' in captured.out\n        assert counts(c)","        assert counts(c)")
text=text.replace("    assert c.run(['connect','codex','--profile','cancel-review','--no-chat'])==0",
    "    command=['connect','codex','--profile','cancel-review','--no-chat'] if mode=='quick' else [\n        'connect','--client','codex','--project',str(c.project),'--profile','cancel-review','--no-chat']\n    assert c.run(command)==0")
text=text.replace("c02=dict(cwd_unmapped=True,git_metadata_usable=False,basename_suggestion_identified=True,",
    "c02=dict(mode=mode,cwd_unmapped=True,git_metadata_usable=False,basename_suggestion_identified=mode=='quick',legacy_selectors_preserved=mode=='legacy',")
text=text.replace("out/'c02-proof.json'","out/('review-proof-'+mode+'.json')")
text=text.replace("assert final['canonical_metadata_revalidation_requested'] is True",
    "assert final['canonical_metadata_revalidation_requested'] is (mode=='quick')")
text=text.replace("out/'g08-proof.json'","out/('g08-proof-'+mode+'.json')")
text=text.replace('canonical_metadata_revalidation_requested=True,effects_started=None,',
    "canonical_metadata_revalidation_requested=mode=='quick',effects_started=None,")
(HERE/'test_review_cancel_v2.py').write_text(text)
(root/'after/tests/quick_connect/test_qc35_review_cancel.py').write_text(text)
installed=Path('C:/Users/jpamb/AppData/Local/Temp/nexus-qc-r1-package-t24_dnfc/venv/Lib/site-packages/okto_nexus/adapters/inbound/cli/connect.py')
before=installed.read_text()
old="""                if answer != 'y':
                    return 0
                approval = saved['review_revision']"""
new="""                if answer != 'y':
                    _display(dict(state='canceled', lifecycle_requested=not args.plan,
                        canonical_metadata_revalidation_requested=canonical_metadata, effects_started=None), args.json)
                    return 0
                approval = saved['review_revision']"""
assert before.count(old)==1
after=before.replace(old,new)
overlay=root/'overlay/connect.py'
overlay.parent.mkdir()
overlay.write_text(after)
import difflib
(HERE/'connect-cancellation-v2.patch').write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),
    fromfile='a/src/okto_nexus/adapters/inbound/cli/connect.py',tofile='b/src/okto_nexus/adapters/inbound/cli/connect.py')))
shutil.copyfile(overlay,HERE/'derived-connect-v2.py.txt')
pins={p.relative_to(REPO).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
    for directory in ('src','tests','docs') for p in (REPO/directory).rglob('*')
    if p.is_file() and '__pycache__' not in p.parts}
(root/'source-pins.json').write_text(json.dumps(pins,indent=2))
(HERE/'allocation.json').write_text(json.dumps(dict(root=str(root),overlay_sha256=hashlib.sha256(overlay.read_bytes()).hexdigest()),indent=2))
runner=(PARENT/'run_derived.py').read_text()
runner=runner.replace('REPO=HERE.parents[2]','REPO=HERE.parents[3]')
runner=runner.replace("HERE/'derived-allocation.json'","HERE/'allocation.json'")
runner=runner.replace("HERE.parent/'qc11-package/allocation.json'","HERE.parents[1]/'qc11-package/allocation.json'")
runner=runner.replace("HERE.parent/'qc08-package/package.py'","HERE.parents[1]/'qc08-package/package.py'")
runner=runner.replace((previous/'overlay/connect.py').as_posix(),overlay.as_posix())
runner=runner.replace("nodes=[('cancel','tests/quick_connect/test_qc35_review_cancel.py'),('choices','tests/quick_connect/test_qc35_id_choice_antecedents.py'),('json-plan','tests/quick_connect/test_quick_connect_cli.py::test_real_http_plan_apply_and_recovery_preserve_public_id_without_test_or_grant_replay')]",
    "nodes=[('variants','tests/quick_connect/test_qc35_review_cancel.py'),('json-plan','tests/quick_connect/test_quick_connect_cli.py::test_real_http_plan_apply_and_recovery_preserve_public_id_without_test_or_grant_replay')]")
(HERE/'run.py').write_text(runner)
print(json.dumps(dict(root=str(root),cases=3,overlay_sha256=hashlib.sha256(overlay.read_bytes()).hexdigest())))
