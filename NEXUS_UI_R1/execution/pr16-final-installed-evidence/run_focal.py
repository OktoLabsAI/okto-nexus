from pathlib import Path
import hashlib
import json
import sys

root=Path(__file__).resolve().parent
mirror=root/'fixture-copy'
assert not (mirror/'src').exists() and sys.flags.isolated
import okto_nexus
import nexus_connector_core
import okto_nexus_connector
import pytest

sys.path.insert(0,str(mirror))
sys.path.insert(0,str(mirror/'tests'))
nodes=[
'tests/home_evolution/test_home_result_artifact_grouping.py::test_newest_foreign_workspace_operation_stays_direct_and_cannot_hide_legitimate_handoff',
'tests/home_evolution/test_home_result_artifact_grouping.py::test_http_result_collects_same_claim_files_once_and_excludes_foreign_claim_and_workspace',
'tests/home_evolution/test_home_result_artifact_grouping.py::test_http_artifact_group_uses_authorized_terminal_relation_with_history_and_other_executor',
'tests/home_evolution/test_home_queries.py::test_result_preview_seen_and_bounded_artifact_metadata',
'tests/home_evolution/test_home_queries.py::test_result_artifact_reference_uses_exact_durable_operation_without_paths',
'tests/home_evolution/test_home_queries.py::test_native_delivery_and_handoff_are_one_activity_then_claim_change_separates_history',
'tests/home_evolution/test_home_final_scope.py::test_project_a_unchanged_when_same_agent_adds_b_work_attention_and_results']
sources={name.split('::')[0]:hashlib.sha256((mirror/name.split('::')[0]).read_bytes()).hexdigest() for name in nodes}
argv=['-c',str(mirror/'pytest.ini'),'--rootdir='+str(mirror),'--confcutdir='+str(mirror/'tests'),*map(lambda n:str(mirror/n),nodes),'-q','-o','pythonpath=','--junitxml='+str(root/'installed-focal.xml')]
code=pytest.main(argv)
origins={name:module.__file__ for name,module in sys.modules.items() if module and getattr(module,'__file__',None) and name.split('.')[0] in ('okto_nexus','nexus_connector_core','okto_nexus_connector')}
assert origins and all(Path(path).resolve().is_relative_to(Path(sys.prefix).resolve()) for path in origins.values()),origins
assert all('okto_labs_okto_nexus' not in value for value in sys.path),sys.path
assert all(hashlib.sha256((mirror/name).read_bytes()).hexdigest()==pin for name,pin in sources.items())
report={'exit_code':code,'nodes':nodes,'pytest_argv':argv,'cwd':str(Path.cwd()),'python':sys.executable,'isolated':sys.flags.isolated,'sys_path':sys.path,'production_module_origins':origins,'all_production_origins_in_new_prefix':True,'fixture_sources_sha256':sources,'fixture_source_drift':[]}
(root/'installed-focal.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
sys.exit(code)
