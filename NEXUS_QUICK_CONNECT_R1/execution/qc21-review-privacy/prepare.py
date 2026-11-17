"""Prepare only two external deltas over the final ten-case Git antecedent."""
import difflib
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
antecedent=Path('C:/Users/jpamb/AppData/Local/Temp/nexus-qc-git-cli-complete-3hnalsq1')
source=antecedent/'after/tests/quick_connect/test_git_cli_integration.py'
before=source.read_text(encoding='utf-8')
assert hashlib.sha256(source.read_bytes()).hexdigest()=='9e6cf1fe0f1c0aaad850ed1f2dbdf6f93dcd031a286bda70d6a30594b90bf78d'
root=Path(tempfile.mkdtemp(prefix='nexus-qc21-review-privacy-')).resolve()
shutil.copytree(antecedent/'after',root/'after',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
assert not (root/'after/src').exists()
shutil.copyfile(antecedent/'pytest.ini',root/'pytest.ini')
# Pin present frozen inputs; the antecedent fixture is separately content pinned.
pins={str(p.relative_to(REPO)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest()
      for directory in ('src','tests','docs') for p in (REPO/directory).rglob('*')
      if p.is_file() and '__pycache__' not in p.parts}
(root/'source-pins.json').write_text(json.dumps(pins,indent=2),encoding='utf-8')
after=before.replace('import json\n','import json\nimport hashlib\n',1)
after=after.replace('def test_origin_first_connect_and_changed_metadata_exact_resume(quick_cli, tmp_path, monkeypatch, capsys, origin):',
    'def test_origin_first_connect_and_changed_metadata_exact_resume(quick_cli, tmp_path, monkeypatch, capsys, caplog, origin):')
privacy='''
    def private_origin_absent(value, label):
        if 'PRIVATE' not in origin:
            return
        text=json.dumps(value,ensure_ascii=False,default=str)
        if any(needle in text for needle in ('PRIVATE',origin,'example.invalid','fake-user','changed.invalid')):
            pytest.fail('Private Git origin metadata reached '+label,pytrace=False)

    def private_checkpoints_absent():
        if 'PRIVATE' not in origin:
            return
        for checkpoint in c.home.rglob('*.json'):
            private_origin_absent(json.loads(checkpoint.read_text()),'owned Nexus checkpoint')
'''
needle="    git('config', '--local', 'remote.origin.url', origin)\n"
assert after.count(needle)==1
after=after.replace(needle,needle+privacy)
after=after.replace("    original_profile = json.loads(profile.read_text())\n",
    "    original_profile = json.loads(profile.read_text())\n    private_checkpoints_absent()\n    private_origin_absent(before,'compared SQLite snapshot')\n")
needle="        resumed = json.loads(capsys.readouterr().out)\n"
assert after.count(needle)==1
after=after.replace(needle,needle+"        private_origin_absent(resumed,'resume JSON')\n        private_origin_absent(snapshot(c.t.deps),'resumed compared SQLite snapshot')\n        private_checkpoints_absent()\n        private_origin_absent([r.getMessage() for r in caplog.records],'captured pytest log messages')\n")
needle="        assert observed_profile == expected_profile\n"
after=after.replace(needle,needle+'''
    if 'PRIVATE' in origin:
        proof=dict(private_parameter=True,checkpoint_json_count=len(list(c.home.rglob('*.json'))),
            compared_tables=list(before),resume_json_count=2,pytest_log_messages=len(caplog.records),
            private_origin_absent=True,git_config_is_excluded_input=True,
            telemetry_scope='Only owned Nexus JSON checkpoints, compared SQLite tables, two resume JSONs and pytest-captured log messages')
        (Path(os.environ['QC_DERIVATIVE_OUTPUT'])/'privacy-proof.json').write_text(json.dumps(proof,indent=2))
''')
needle="""        assert len(prompts) == 1
        return 'y'
"""
assert after.count(needle)==1
after=after.replace(needle,"""        assert len(prompts) == 1
        captured=capsys.readouterr()
        review_text=captured.out
        checkpoint,=(c.home/'terminal/profiles').glob('*.json')
        retained=json.loads(checkpoint.read_text())
        assert retained['state']=='review'
        selection=retained['selection']
        request=retained['review_request']
        config=request['configuration']
        assert selection['label']=='ancestor-logical'
        assert selection['quick_connect']['project_name_source']=='git_origin'
        assert selection['quick_connect']['cwd_resolution']['invocation_cwd']==str(c.project)
        assert selection['project']==config['workspace_root']==str(c.project)
        assert config['adapter_id']=='codex_app_server'
        proposed=request['public_connection']['connect_id']
        assert proposed==selection['public_connection']['connect_id']=='codex'
        required={
            'name': 'ancestor-logical', 'source':'Project name source: git_origin',
            'cwd':'Invocation directory: '+str(c.project),
            'root':'Project: '+str(c.project), 'host':'Execution host: '+request['executor_id'],
            'adapter':'Harness: '+config['adapter_id'], 'proposed_id':'ID do Harness (proposed): '+proposed}
        assert all(text in review_text for text in required.values())
        effects=retained['effects']
        assert effects and all('- '+effect in review_text for effect in effects)
        assert c.t.turns==c.t.probes==[]
        proof=dict(before_confirmation=True,checkpoint_state='review',
            displayed_fields=list(required),effect_count=len(effects),all_effects_printed=True,
            tests=0,probes=0,checkpoint_sha256=hashlib.sha256(checkpoint.read_bytes()).hexdigest())
        (Path(os.environ['QC_DERIVATIVE_OUTPUT'])/'review-proof.json').write_text(json.dumps(proof,indent=2))
        # Recompose captured output so original downstream output assertions keep
        # the same entire transcript; no production display behavior is changed.
        print(captured.out,end='')
        if captured.err:
            print(captured.err,end='',file=__import__('sys').stderr)
        return 'y'
""")
(root/'after/tests/quick_connect/test_git_cli_integration.py').write_text(after,encoding='utf-8')
(HERE/'test-delta.patch').write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),
    fromfile='antecedent/test_git_cli_integration.py',tofile='qc21/test_git_cli_integration.py')),encoding='utf-8')
(HERE/'executed-test.py').write_text(after,encoding='utf-8')
(HERE/'allocation.json').write_text(json.dumps(dict(root=str(root)),indent=2),encoding='utf-8')
runner=(HERE.parent/'qc15-cli-choice-scenarios/run.py').read_text(encoding='utf-8')
runner=runner.replace("nodes=[('choices','tests/execution_r4/test_qc15_cli_choices.py')]",
    "nodes=[('review-privacy','tests/quick_connect/test_git_cli_integration.py')]")
runner=runner.replace("'-v','-s','-x','--tb=short'", "'-v','-s','-x','-k','monorepo or PRIVATE','--tb=short'")
(HERE/'run.py').write_text(runner,encoding='utf-8')
print(json.dumps(dict(root=str(root),antecedent_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
    executed_sha256=hashlib.sha256(after.encode()).hexdigest(),selected_cases=2)))
