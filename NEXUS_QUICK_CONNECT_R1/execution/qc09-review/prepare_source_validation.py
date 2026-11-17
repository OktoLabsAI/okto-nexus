"""Prepare the released 53-case source cut over unchanged PR27 dependencies."""
import hashlib
import json
from pathlib import Path
import tempfile

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
root = Path(tempfile.mkdtemp(prefix='nexus-qc-compat-source-')).resolve()
(HERE / 'source-validation-allocation.json').write_text(json.dumps(dict(root=str(root)), indent=2), encoding='utf-8')
paths = [p for p in (REPO / 'src').rglob('*') if p.is_file() and '__pycache__' not in p.parts]
paths.extend(REPO / name for name in ('tests/quick_connect/test_entry_compatibility.py',
    'tests/execution_r4/test_connection_catalog.py', 'tests/execution_r4/test_terminal_multi_harness.py'))
pins = {p.relative_to(REPO).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
(root / 'source-pins.json').write_text(json.dumps(pins, indent=2), encoding='utf-8')
(root / 'pytest.ini').write_text('[pytest]\nasyncio_mode=auto\nasyncio_default_fixture_loop_scope=function\n'
    'pythonpath=' + str(REPO / 'tests') + ' ' + str(REPO / 'tests/execution_r4') + '\n', encoding='utf-8')
runner = (HERE / 'run_derivative.py').read_text(encoding='utf-8')
runner = runner.replace("HERE/'derivative-allocation.json'", "HERE/'source-validation-allocation.json'")
runner = runner.replace("package=Path(json.loads((HERE.parent/'qc08-package/allocation.json').read_text())['root']).resolve()",
    "package=Path(r'C:/Users/jpamb/AppData/Local/Temp/nexus-ui-r3-harness-pr27-gsg_twh1').resolve()")
start = runner.index('def payload():')
end = runner.index('\n\nplugin=', start)
runner = runner[:start] + '''def payload():
    site=package/'venv/Lib/site-packages'
    return {str(p.relative_to(site)):hashlib.sha256(p.read_bytes()).hexdigest()
        for module in ('okto_nexus','nexus_connector_core','okto_nexus_connector')
        for p in (site/module).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc'}
''' + runner[end:]
runner = runner.replace("assert all(pathlib.Path(value).resolve().is_relative_to(PREFIX) for value in origins.values()),origins",
    "assert pathlib.Path(origins['okto_nexus']).resolve().is_relative_to(pathlib.Path(%r)),origins\n    assert all(pathlib.Path(value).resolve().is_relative_to(PREFIX) for name,value in origins.items() if name!='okto_nexus'),origins" % str(REPO / 'src'))
runner = runner.replace("(root/'after/conftest.py').write_text(plugin,encoding='utf-8')", "(root/'release_plugin.py').write_text(plugin,encoding='utf-8')")
start = runner.index("nodes=[('mutable-feature'")
end = runner.index('\nfor label,node in nodes:', start)
runner = runner[:start] + 'nodes=' + repr([
    ('compatibility-50', 'tests/quick_connect/test_entry_compatibility.py'),
    ('canonical-shortcut', 'tests/execution_r4/test_connection_catalog.py::test_cli_existing_canonical_without_profile_creates_only_shortcut'),
    ('single-harness', 'tests/execution_r4/test_terminal_multi_harness.py::test_single_observed_harness_needs_no_profile_and_existing_connection_offers_all_intents'),
    ('two-harnesses', 'tests/execution_r4/test_terminal_multi_harness.py::test_two_distinct_harnesses_share_project_keep_custom_a_and_recover_b_finish')]) + runner[end:]
runner = runner.replace("'-I','-B','-m','pytest'", "'-I','-B','-c',\"import sys,runpy;sys.path[:0]=\"+repr([str(REPO/'src'),str(root)])+\";runpy.run_module('pytest',run_name='__main__')\",'-p','release_plugin'")
runner = runner.replace("'--rootdir='+str(root/'after'),'--confcutdir='+str(root/'after'),str(root/'after'/node)",
    "'--rootdir='+str(REPO),'--confcutdir='+str(REPO/'tests'),str(REPO/node)")
runner = runner.replace('app_source_present=False', "app_source_present=True, qualification='SOURCE_ONLY_PR27_DEPENDENCIES'")
(HERE / 'run_source_validation.py').write_text(runner, encoding='utf-8')
print(json.dumps(dict(root=str(root), source_pins=len(pins))))
