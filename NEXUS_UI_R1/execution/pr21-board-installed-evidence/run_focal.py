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
nodes=['tests/ui_simplification/test_home_board.py', 'tests/ui_simplification/test_entry_app_integration.py', 'tests/ui_simplification/test_entry_related.py::test_attention_preview_and_pages_preserve_five_canonical_questions', 'tests/ui_simplification/test_entry_related.py::test_results_preview_and_pages_preserve_five_canonical_deliveries', 'tests/home_evolution/test_home_result_artifact_grouping.py']
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
