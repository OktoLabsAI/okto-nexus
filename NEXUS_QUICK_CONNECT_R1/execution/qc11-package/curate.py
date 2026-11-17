"""Curate QC033 package-only evidence; installed suite belongs to another owner."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
root=Path(json.loads((HERE/'allocation.json').read_text())['root']).resolve()
spec=importlib.util.spec_from_file_location('qc11_package',HERE/'package.py')
builder=importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
build=json.loads((root/'build-manifest.json').read_text())
audit=json.loads((root/'installed-audit.json').read_text())
payload=json.loads((root/'payload-manifest.json').read_text())
before=build['source_pins']
after=builder.pins()
changed=sorted(name for name in before.keys()|after.keys() if before.get(name)!=after.get(name))
(root/'source-pins-after.json').write_text(json.dumps(after,indent=2)+'\n',encoding='utf-8')
assert not changed,changed
assert audit['versions']=={'okto-nexus':'0.3.6','okto-nexus-connector-core':'0.0.14','okto-nexus-connector':'0.0.13'}
assert all(module['equal_installed_wheel'] for module in audit['modules'].values())
assert audit['modules']['okto_nexus']['equal_checkout_source']
assert len(payload['okto_nexus'])==732 and len(payload['nexus_connector_core'])==168 and len(payload['okto_nexus_connector'])==127
assert all(row['exit_code']==row['expected'] for row in audit['commands'])
assert all(not any(Path(name).name.lower().endswith(suffix) for suffix in
                  ('.db','.sqlite','.sqlite3','.db-wal','.db-shm','.env')) for files in payload.values() for name in files)
commands=json.loads((root/'commands.json').read_text())
assert commands[-1]['label']=='installed-audit' and commands[-1]['exit_code']==0
probe='import importlib.metadata,json;print(json.dumps({d.metadata["Name"]:d.version for d in importlib.metadata.distributions()},sort_keys=True))'
result=subprocess.run(['rtk','proxy',str(root/'venv/Scripts/python.exe'),'-I','-c',probe],cwd=root,
                      env=builder.environment(root),capture_output=True,text=True,timeout=30)
assert result.returncode==0,result.stderr
dependencies=json.loads(result.stdout)
report=dict(version=1,created_at=datetime.now(timezone.utc).isoformat(),status='PASS_BUILD_INSTALL_SMOKE',
    source_candidate_commit='fa031697b37a1b879d855f7858f01320addf0df7',commit_origin='Parent SOURCE_READY; file hashes are authoritative',
    root=str(root),python=str(root/'venv/Scripts/python.exe'),environment_frozen=True,
    python_version=audit['python'],OS=audit['OS'],package_versions=audit['versions'],dependencies=dependencies,
    artifacts={name:pin for name,pin in build['artifacts'].items() if name.endswith(('.whl','.tar.gz'))},
    dependency_artifacts={name:dict(sha256=audit['modules'][name]['wheel_sha256'],rebuilt=False)
                          for name in ('nexus_connector_core','okto_nexus_connector')},
    gates=dict(base_core_without_connector_or_torch='PASS; ci/base-with-core.log',
               serve_lite_dev_without_connector_or_torch='PASS; ci/local-without-connector.log',
               connector_added_after_local_gate='PASS; exact pinned wheel',
               ci_installed_smoke='PASS',pip_check='PASS',twine='PASS four exact artifacts; Nexus wheel/sdist + unchanged Core/Connector wheels'),
    modules=audit['modules'],source_comparison_scope='All Nexus module payload bytes equal installed/wheel/checkout/isolated source/sdist. Core and Connector compare installed against immutable pinned vendor wheels; sibling checkouts are not re-qualified.',
    payload_counts={name:dict(files=len(files),suffixes=dict(Counter(Path(path).suffix for path in files)))
                    for name,files in payload.items()},
    assets=audit['assets'],entrypoints=audit['commands'],
    invalid_argv=audit.get('badflag_json'),
    isolation=dict(isolated=audit['isolated'],cwd=audit['cwd'],sys_path=audit['sys_path'],
        prefix=audit['prefix'],origin_guard='Every application/Core/Connector import inside this own site-packages',
        help_subprocess_path_empty=True,child_environment='System executable allowlist; own TEMP/HOME/APPDATA/LOCALAPPDATA; no provider/CLI auth env copied; pip config NUL'),
    source_snapshot=dict(files=len(before),before='source-pins-before.json',after='source-pins-after.json',drift=changed,
        scope='src all payload, frontend sources/public/build inputs, tests, packaging metadata, lock, CI helpers/vendor manifest',
        not_copied_into_sdist='docs, tests, plans and repository tooling. Build source is src plus packaging metadata; no full-documentation sdist claim.'),
    cleanup=dict(all_owned_build_install_smoke_probe_commands_terminal=True,force_used=False,
        standalone_service_or_model_started=False,prefix_retained_for_separate_installed_test_owner=True),
    limits=['No full installed pytest campaign in this report; delegated separately after READY.',
        'No provider/native harness execution, authentication access, personal install, release or upload.',
        'No Linux or Python3.11/3.12 matrix claim.',
        'No Vite rebuild; Root frozen index-CfDr8rCI static payload reused and byte verified.',
        'Previous BXP/BGONN/PR16/PR18/PR21/PR27 prefixes/artifacts not reinstalled or replaced.'],
    commands=commands)
evidence=HERE/'evidence'
evidence.mkdir(exist_ok=True)
for name in ('build-manifest.json','source-pins-before.json','source-pins-after.json','payload-manifest.json',
             'installed-audit.json','commands.json',
             'twine.log','pip-check.log','ci-install.log','ci-smoke.log','installed-audit.log',
             'nexus-help.log','connector-help.log','codex-help.log','claude-help.log','pi-help.log','badflag-json.log'):
    shutil.copyfile(root/name,evidence/name)
for name in ('base-with-core.log','local-without-connector.log','installed.json'):
    shutil.copyfile(root/'ci'/name,evidence/name)
(HERE/'qualification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
manifest={str(p.relative_to(HERE)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest()
          for p in HERE.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name!='manifest.json'}
(HERE/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(report=str(HERE/'qualification.json'),sha256=hashlib.sha256((HERE/'qualification.json').read_bytes()).hexdigest(),
                     source_files=len(before),source_drift=changed,payload_files=sum(len(files) for files in payload.values()))))
