"""Copy selected immutable tests and create actual POSIX-filesystem cases."""
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path('/tmp/nexus-qc28-xmlie7rv')
REPO = Path('/mnt/d/Projetos/Techridy/okto_labs_okto_nexus')
assert (ROOT / 'package-ready.json').exists()
tests = ROOT / 'tests'
tests.mkdir()
for name in ('cwd', 'test-output', 'test-tmp'):
    (ROOT / name).mkdir()
names = ['test_connect_arguments.py', 'test_git_project_hint.py', 'test_git_project_trust.py',
         'test_quick_connect_project.py', 'test_quick_connect_id_choices.py']
pins = {}
for name in names:
    source = REPO / 'tests/quick_connect' / name
    target = tests / name
    shutil.copyfile(source, target)
    assert source.read_bytes() == target.read_bytes()
    pins[str(source.relative_to(REPO))] = hashlib.sha256(source.read_bytes()).hexdigest()
(ROOT / 'copied-test-pins.json').write_text(json.dumps(pins, indent=2) + '\n')
(ROOT / 'pytest.ini').write_text('[pytest]\nasyncio_mode=auto\nasyncio_default_fixture_loop_scope=function\n')
(tests / 'test_posix_physical_paths.py').write_text('''"""Actual Linux FS identity; no canonical-authority DTOs or runtime execution."""
import os
from pathlib import Path

from okto_nexus.adapters.inbound.cli.connect import project_profile
from okto_nexus.adapters.outbound.git_project_hint import discover_project_name
from okto_nexus.application.execution_local_realizations import directory_identity
from okto_nexus.application.terminal_connection import _same_local_path


def test_c15_real_case_sensitive_repo_and_repo_are_distinct(tmp_path):
    assert os.name == 'posix'
    upper, lower = tmp_path / 'Repo', tmp_path / 'repo'
    upper.mkdir()
    lower.mkdir()
    assert not upper.samefile(lower)
    u, l = directory_identity(str(upper)), directory_identity(str(lower))
    assert u['path'] == str(upper) and l['path'] == str(lower)
    assert (u['device'], u['inode']) != (l['device'], l['inode'])
    up, uid = project_profile(upper, None)
    lo, lid = project_profile(lower, None)
    assert up == str(upper) and lo == str(lower) and uid != lid
    assert not _same_local_path(up, lo)
    assert discover_project_name(upper, plan=True).name == 'Repo'
    assert discover_project_name(lower, plan=True).name == 'repo'


def test_posix_symlink_resolves_same_physical_identity_and_profile(tmp_path):
    physical, link = tmp_path / 'Physical', tmp_path / 'LogicalLink'
    physical.mkdir()
    link.symlink_to(physical, target_is_directory=True)
    assert link.is_symlink() and link.samefile(physical)
    assert directory_identity(str(link)) == directory_identity(str(physical))
    assert project_profile(link, None) == project_profile(physical, None)
    assert project_profile(link, None)[0] == str(physical)


def test_posix_backslash_is_filename_not_directory_separator(tmp_path):
    (tmp_path / 'folder').mkdir()
    slash = tmp_path / 'folder' / 'leaf'
    backslash = tmp_path / r'folder\\leaf'
    slash.mkdir()
    backslash.mkdir()
    assert slash.is_dir() and backslash.is_dir() and not slash.samefile(backslash)
    assert project_profile(slash, None)[0] != project_profile(backslash, None)[0]
    assert directory_identity(str(slash)) != directory_identity(str(backslash))
    assert not _same_local_path(str(slash), str(backslash))
''')
plugin = '''import importlib,importlib.metadata,json,os,pathlib,sys
import pytest
PREFIX=pathlib.Path('/tmp/nexus-qc28-xmlie7rv/venv').resolve()
OUT=pathlib.Path(os.environ['QC28_OUTPUT'])
NAMES=('okto_nexus','nexus_connector_core','okto_nexus_connector')
def origins():
    return {name:str(pathlib.Path(importlib.import_module(name).__file__).resolve()) for name in NAMES}
def pytest_sessionstart(session):
    value=origins()
    assert pathlib.Path(sys.prefix).resolve()==PREFIX
    assert sys.flags.isolated and sys.dont_write_bytecode
    assert all(pathlib.Path(p).is_relative_to(PREFIX) for p in value.values())
    (OUT/'origins-start.json').write_text(json.dumps(dict(origins=value,sys_path=sys.path,prefix=sys.prefix,python=sys.version),indent=2))
def pytest_sessionfinish(session,exitstatus):
    bad={n:getattr(m,'__file__',None) for n,m in sys.modules.items() if n.split('.')[0] in NAMES and getattr(m,'__file__',None) and not pathlib.Path(m.__file__).resolve().is_relative_to(PREFIX)}
    (OUT/'origins-finish.json').write_text(json.dumps(dict(origins=origins(),bad=bad,exitstatus=exitstatus),indent=2))
    assert not bad
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item,call):
    result=yield
    report=result.get_result()
    value=dict(nodeid=report.nodeid,when=report.when,outcome=report.outcome,duration=report.duration)
    if report.failed:value['failure']=report.longreprtext
    with (OUT/'reports.jsonl').open('a') as f:f.write(json.dumps(value)+'\\n')
    print('IMMEDIATE_REPORT '+json.dumps(value),flush=True)
'''
(tests / 'conftest.py').write_text(plugin)
print(json.dumps(dict(copied_tests=names, extra_cases=3, copied_src=False)))
