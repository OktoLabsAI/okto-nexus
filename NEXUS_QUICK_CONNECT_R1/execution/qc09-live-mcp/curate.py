"""Finalize the one completed installed LiveMCP run, without rerunning it."""
import hashlib
import importlib.util
from importlib import metadata
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
report=json.loads((HERE/'qualification.json').read_text())
assert sys.flags.isolated and sys.dont_write_bytecode
prefix=Path(sys.prefix).resolve()
assert prefix==Path(report['python']).parents[1]
cleanup=json.loads((HERE/'cleanup-physical.json').read_text(encoding='utf-8-sig'))
assert cleanup=={'processes':[],'listeners':[]}
raw=(HERE/'live-raw.log').read_text(encoding='utf-8')
assert raw.rstrip().endswith('LIVE E2E RESULT: PASS') and report['exit_code']==0
assert report['summary']['cleanup']=={'physical_exit':True,'exit_code':0,'canonical_stop_exit_code':0}
assert not report['script_drift'] and not report['installed_payload_drift']
assert not report['script_allocated_roots_remaining']
report['module_origins']={name:importlib.util.find_spec(name).origin for name in ('okto_nexus','nexus_connector_core','mcp')}
assert all(Path(value).resolve().is_relative_to(prefix) for value in report['module_origins'].values())
report['versions']={name:metadata.version(name) for name in ('okto-nexus','okto-nexus-connector-core','mcp')}
report['physical_cleanup']=dict(processes=[],listeners=[],port=56195,proof='cleanup-physical.json',force_used=False,
    deleted='Only script-allocated okto-live-http-mcp-* root, after canonical stop and owned process wait.',
    retained='Outer driver root contains only logs/profile directories; no DB archived into repository.')
report['executed_driver']='run-executed.txt'
report['executed_driver_sha256']=hashlib.sha256((HERE/'run-executed.txt').read_bytes()).hexdigest()
report['driver_postrun_change']='Unused import removed and lambda changed to def for Ruff only; literal executed driver retained. LiveMCP was not repeated.'
report['source_script_sha256_after']=hashlib.sha256((REPO/'scripts/live_client.py').read_bytes()).hexdigest()
assert report['source_script_sha256_after']==report['script_sha256']
report['scope_limit']='Real installed HTTP MCP coordination smoke, not a model/native harness campaign or CI platform matrix.'
(HERE/'qualification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
manifest={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in HERE.iterdir()
          if p.is_file() and p.name!='manifest.json'}
(HERE/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
manifest={str(p.relative_to(HERE)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest()
    for p in HERE.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name!='manifest.json'}
(HERE/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(status='PASS',report_sha256=hashlib.sha256((HERE/'qualification.json').read_bytes()).hexdigest(),
                     tools=report['summary']['tools_count'],provider_calls=0,physical_cleanup=cleanup)))
