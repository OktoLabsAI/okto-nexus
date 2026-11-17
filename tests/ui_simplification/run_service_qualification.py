"""Finite installed-only service regressions; never installs a user service.

Run using the explicitly allocated -I Python prefix. Nexus cases own real child
Servers and inert native peers; Connector cases inject FakeTasks/IPC/processes.
Private homes and logs remain in the unique Temp allocation until audited cleanup.
"""
from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
import hashlib
from importlib import import_module, metadata
import json
from pathlib import Path
import sys
import tempfile
import time
import xml.etree.ElementTree as ET


ROOT=Path(__file__).resolve().parents[2]
CONNECTOR=ROOT.parent/'okto-nexus-connector'
DEST=ROOT/'NEXUS_UI_R1/execution/evidence/pr07-service'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def installed_snapshot():
    packages={}
    for distribution,name in [('okto-nexus','okto_nexus'),('okto-nexus-connector','okto_nexus_connector'),
                              ('okto-nexus-connector-core','nexus_connector_core')]:
        module=import_module(name)
        origin=Path(module.__file__).resolve()
        assert origin.is_relative_to(Path(sys.prefix).resolve()),(name,str(origin))
        entries={str(path.relative_to(origin.parent)).replace('\\','/'):digest(path)
                 for path in sorted(origin.parent.rglob('*'))
                 if path.is_file() and '__pycache__' not in path.parts and path.suffix!='.pyc'}
        packages[distribution]=dict(version=metadata.version(distribution),origin=str(origin),
            payload_files=len(entries),payload_sha256=hashlib.sha256(json.dumps(entries,sort_keys=True).encode()).hexdigest())
    return dict(python=sys.executable,isolated=sys.flags.isolated,prefix=sys.prefix,packages=packages)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--surface',choices=['nexus','connector','connector-controls','nexus-passive'],required=True)
    args=parser.parse_args()
    assert sys.flags.isolated==1,'Use -I; checkout product imports are forbidden.'
    private=Path(tempfile.mkdtemp(prefix='nexus-ui-r1-service-'+args.surface+'-'))
    DEST.mkdir(parents=True,exist_ok=True)
    before=installed_snapshot()
    repo=ROOT if args.surface.startswith('nexus') else CONNECTOR
    sys.path[:0]=[str(repo),str(repo/'tests')]
    if args.surface=='nexus':
        tests=[ROOT/'tests/test_terminal_connect_process.py',ROOT/'tests/execution_r4/test_service_restart_contracts.py']
    elif args.surface=='connector':
        source=CONNECTOR/'tests/unit/test_configure_login_start.py'
        tests=[str(source)+'::test_disabled_task_requires_enable_review_and_later_disable_is_preserved',
               str(source)+'::test_existing_task_reuse_or_lost_enablement_receipt_does_not_recreate']
    elif args.surface=='connector-controls':
        source=CONNECTOR/'tests/unit/test_user_service_lifecycle.py'
        tests=[str(source)+'::test_active_disable_does_not_stop_or_change_generation_control',
               str(source)+'::test_enablement_response_loss_recovers_without_another_native_effect',
               str(CONNECTOR/'tests/unit/test_service_upgrade.py')+'::test_disabled_task_remains_disabled',
               CONNECTOR/'tests/integration/test_passive_cli.py']
    else:
        source=ROOT/'tests/test_service_inspection.py'
        tests=[str(source)+'::test_status_of_absent_instance_does_not_create_home_or_start_process',
               str(source)+'::test_remote_target_is_not_silently_treated_as_local',
               str(ROOT/'tests/test_service_status_missing_discovery.py')+'::test_status_inspects_absence_with_missing_saved_or_explicit_root']
    source_paths=[ROOT/'tests/test_terminal_connect_process.py',ROOT/'tests/execution_r4/test_service_restart_contracts.py',
                  ROOT/'tests/execution_r4/remote_renewal_helpers.py',
                  CONNECTOR/'tests/unit/test_configure_login_start.py',CONNECTOR/'tests/unit/test_user_service_lifecycle.py']
    source_paths.extend([ROOT/'tests/test_service_inspection.py',ROOT/'tests/test_service_status_missing_discovery.py',
                         CONNECTOR/'tests/unit/test_service_upgrade.py',CONNECTOR/'tests/integration/test_passive_cli.py'])
    sources={str(path):digest(path) for path in source_paths}
    import pytest
    report=DEST/(args.surface+'-tests.xml')
    command=['-c','nul','--rootdir='+str(repo),'--confcutdir='+str(repo/'tests'),'-p','no:cacheprovider',
        '-o','asyncio_mode=auto','-o','asyncio_default_fixture_loop_scope=function',
        '--basetemp='+str(private/'pytest'),'-q','--tb=short','--junitxml='+str(report),*map(str,tests)]
    started=time.monotonic()
    (DEST/(args.surface+'-start.json')).write_text(json.dumps(dict(private_root=str(private),installed=before),indent=2)+'\n',encoding='utf-8')
    with (private/'pytest-private.log').open('w',encoding='utf-8') as stream,redirect_stdout(stream),redirect_stderr(stream):
        code=pytest.main(command)
    after=installed_snapshot()
    changed=[name for name in before['packages'] if before['packages'][name]!=after['packages'][name]]
    testcase=[]
    if report.exists():
        for node in ET.parse(report).iter('testcase'):
            testcase.append(dict(name=node.get('name'),classname=node.get('classname'),
                outcome='FAIL' if node.find('failure') is not None or node.find('error') is not None else
                        'SKIP' if node.find('skipped') is not None else 'PASS'))
    result=dict(surface=args.surface,private_root=str(private),exit_code=int(code),seconds=time.monotonic()-started,
        installed_before=before,installed_after=after,changed_installed_payloads=changed,
        test_sources_sha256=sources,changed_test_sources=[str(p) for p in source_paths if digest(p)!=sources[str(p)]],
        pytest_arguments=command,cases=testcase,provider_calls=0,personal_installation_changed=False,
        native_scheduler_calls=False,scope='Real isolated Server process lifecycle and synthetic remote native peer' if args.surface=='nexus'
            else 'Real persisted service-plan/checkpoint logic with FakeTasks, fake IPC and fake process status')
    (DEST/(args.surface+'-qualification.json')).write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(surface=args.surface,exit_code=int(code),cases=testcase,private_root=str(private),payload_drift=changed)))
    raise SystemExit(code)


if __name__=='__main__':
    main()
