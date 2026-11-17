"""Create only a disposable test/helper derivative; application stays installed."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
allocation=HERE/'derivative-allocation.json'
assert not allocation.exists(), 'Preserve a previous derivative, never silently retry in a new root.'
root=Path(tempfile.mkdtemp(prefix='nexus-qc09-fixture-derivative-')).resolve()
allocation.write_text(json.dumps({'root':str(root)},indent=2)+'\n',encoding='utf-8')
index={}
for directory in (REPO/'tests/execution_r4',REPO/'tests'):
    for path in sorted(directory.glob('*.py')):
        index.setdefault(path.stem,path)
selected=set()
queue=[index[name] for name in ('test_canonical_admission_shutdown','test_canonical_handoff_recovery',
                               'test_canonical_capture_admission')]
queue.extend((REPO/'tests/conftest.py',REPO/'tests/execution_r4/conftest.py'))
while queue:
    path=queue.pop()
    if path in selected:
        continue
    selected.add(path)
    tree=ast.parse(path.read_text(encoding='utf-8-sig'))
    for node in ast.walk(tree):
        names=[]
        if isinstance(node,ast.Import):
            names=[value.name.split('.')[0] for value in node.names]
        elif isinstance(node,ast.ImportFrom) and node.module:
            names=[node.module.split('.')[0]]
        queue.extend(index[name] for name in names if name in index and index[name] not in selected)
for path in (REPO/'tests/legacy_native_fixture').rglob('*.py'):
    selected.add(path)
for relative in ('tests/__init__.py','tests/execution_r4/__init__.py'):
    if (REPO/relative).exists():
        selected.add(REPO/relative)
data=list((REPO/'plans/contratos').glob('*.json'))
pins={}
for path in sorted(selected|set(data)):
    relative=path.relative_to(REPO)
    pins[relative.as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
    for stage in ('before','after'):
        target=root/stage/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(path,target)
assert not (root/'after/src').exists()
shutdown=root/'after/tests/execution_r4/test_canonical_admission_shutdown.py'
text=shutdown.read_text(encoding='utf-8')
text=text.replace('def test_feature_disable_preserves_unprojected_terminal_and_exclusive_claim(connected_local, monkeypatch):',
    'def test_feature_disable_preserves_unprojected_terminal_and_exclusive_claim(mutable_connected_local, monkeypatch):')
needle="    setup, binding, native = connected_local\n    enable(setup, binding)"
assert text.count(needle)==1
text=text.replace(needle,"    setup, binding, native = mutable_connected_local\n    enable(setup, binding)")
fixture='''

import pytest
from contextlib import contextmanager
from types import SimpleNamespace


@pytest.fixture
def mutable_connected_local(tmp_path, monkeypatch):
    import test_local_realization as realization
    from okto_nexus.bootstrap.dependencies import bootstrap
    from okto_nexus.adapters.inbound.http.app import build_app

    def mutable_app_for(home):
        deps = bootstrap({}, ["--home", str(home),
            "--runtime-handoff-auto-claim-enabled", "false"])
        return deps, build_app(deps)

    monkeypatch.setattr(realization, "app_for", mutable_app_for)
    with contextmanager(realization.local_setup.__wrapped__)(tmp_path, monkeypatch,
            SimpleNamespace(param="codex_app_server")) as setup:
        response = setup[2].get("/api/v1/settings", headers=setup[3]["operator"])
        assert response.status_code == 200, response.text
        setting = next(item for item in response.json()["data"]["items"]
                       if item["key"] == "feature_harness_integrations")
        assert setting["value"] is True and setting["editable"] is True, setting
        assert setting["source"] == "default", setting
        yield connected_local.__wrapped__(setup)
'''
shutdown.write_text(text+fixture,encoding='utf-8')
structured=root/'after/tests/execution_r4/test_canonical_structured_work.py'
text=structured.read_text(encoding='utf-8')
start=text.index('    peers = []\n    class Factory:')
end=text.index('    hid, grant, claim, call = prepare',start)
text=text[:start]+'''    # Reuse the full canonical launch/guard/birth/handshake test boundary.
    from test_canonical_native_protocol_regressions import install_native
    peers, _ = install_native(connected, source)
'''+text[end:]
structured.write_text(text,encoding='utf-8')
changed=[]
diff=[]
for relative,pin in pins.items():
    path=root/'after'/relative
    if hashlib.sha256(path.read_bytes()).hexdigest()!=pin:
        changed.append(relative)
        diff.extend(difflib.unified_diff((root/'before'/relative).read_text(encoding='utf-8').splitlines(True),
            path.read_text(encoding='utf-8').splitlines(True),fromfile='a/'+relative,tofile='b/'+relative))
(root/'changes.patch').write_text(''.join(diff),encoding='utf-8')
assert changed==sorted(['tests/execution_r4/test_canonical_admission_shutdown.py',
                        'tests/execution_r4/test_canonical_structured_work.py']),changed
(root/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n',encoding='utf-8')
(root/'pytest.ini').write_text('[pytest]\nasyncio_mode=auto\nasyncio_default_fixture_loop_scope=function\n'
    'pythonpath=after/tests after/tests/execution_r4\n',encoding='utf-8')
report=dict(root=str(root),copied_files=len(pins),changed_test_files=changed,app_source_copied=False,
            application='Installed frozen prefix0s9w2_3_; no package edits or installs')
(HERE/'derivative-prepare.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report))
