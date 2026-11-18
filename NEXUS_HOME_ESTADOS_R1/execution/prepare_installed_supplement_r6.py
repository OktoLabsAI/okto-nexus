"""Prepare a post-build test closure; do not allocate or run it."""
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent
target = HERE / 'installed-supplement-r6'
assert not target.exists()
target.mkdir()
source = (HERE / 'package-hst-r5/installed_regression.py').read_text(encoding='utf-8')
old = "spec=importlib.util.spec_from_file_location('hst_builder',HERE/'package.py')"
assert source.count(old) == 1
source = source.replace(old, "PACKAGE=HERE.parent/'package-hst-r6'\n" +
    "spec=importlib.util.spec_from_file_location('hst_builder',PACKAGE/'package.py')")
for name in ('allocation.json', 'READY.json', 'SOURCE_ASSET_READY.json'):
    source = source.replace("(HERE/'" + name + "')", "(PACKAGE/'" + name + "')")
old = "    expected=build['source_pins']"
new = """    expected=dict(build['source_pins'])
    supplement=json.loads((HERE/'TESTS_READY.json').read_text())
    assert supplement['runtime_source_commit']==frozen['source_commit']
    assert supplement['runtime_wheel_sha256']==ready['wheel_sha256']
    assert args.tests==supplement['selections']
    # Exactly one new test file is allowed. No baseline source, frontend,
    # existing test, helper, lock or dependency byte may be replaced.
    assert set(supplement['additions'])=={'tests/home_states/test_results_boundary_completion.py'}
    for name,pin in supplement['additions'].items():
        assert name not in expected and len(pin)==64
        expected[name]=pin"""
assert source.count(old) == 1
source = source.replace(old, new)
old = "    root=Path(tempfile.mkdtemp(prefix='nexus-hst-installed-'))"
new = """    assert not (HERE/'allocation.json').exists(), 'Preserve prior supplemental cuts.'
    root=Path(tempfile.mkdtemp(prefix='nexus-hst-supplement-'))
    (HERE/'allocation.json').write_text(json.dumps(dict(root=str(root)),indent=2)+'\\n',encoding='utf-8')
    (root/'TESTS_READY.json').write_text(json.dumps(supplement,indent=2)+'\\n',encoding='utf-8')"""
assert source.count(old) == 1
source = source.replace(old, new)
old = 'build_source_pin_count=len(expected)'
assert source.count(old) == 1
source = source.replace(old, "base_build_source_pin_count=len(build['source_pins'])," +
    "additional_test_pins=supplement['additions'],guarded_source_test_pin_count=len(expected)," +
    "runtime_source_commit=frozen['source_commit'],test_closure_scope='Post-build supplement; no application artifact rebuilt or mutated'")
(target / 'installed_regression.py').write_text(source, encoding='utf-8')
shutil.copyfile(HERE / 'package-hst-r6/owned_commands.py', target / 'owned_commands.py')
print(target)
