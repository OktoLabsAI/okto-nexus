"""Single installed HTTP/MCP smoke, gated by final package READY; provider zero."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import zipfile

import package as builder
from owned_commands import run_owned

HERE = Path(__file__).resolve().parent
REPO = builder.REPO


def payload(ready):
    result = {}
    prefix = Path(ready['root'])/'venv/Lib/site-packages'
    artifacts = [(Path(ready['wheel']), 'okto_nexus'),
        (REPO/'vendor/wheels/okto_nexus_connector_core-0.0.14-py3-none-any.whl', 'nexus_connector_core'),
        (REPO/'vendor/ci/okto_nexus_connector-0.0.13-py3-none-any.whl', 'okto_nexus_connector')]
    for wheel, module in artifacts:
        with zipfile.ZipFile(wheel) as archive:
            for name in archive.namelist():
                if name.startswith(module+'/') and not name.endswith('/'):
                    data = (prefix/name).read_bytes()
                    assert data == archive.read(name), name
                    result[name] = hashlib.sha256(data).hexdigest()
    assert len(result) == ready['payload_files']
    return result


def main():
    builder.source_ready()
    ready = json.loads((HERE/'READY.json').read_text(encoding='utf-8'))
    assert ready['ready'] and ready['version'] == '0.3.7' and ready['prefix_frozen']
    assert builder.sha(Path(ready['wheel'])) == ready['wheel_sha256']
    script = REPO/'scripts/live_client.py'
    plan = json.loads((HERE.parent/'installed-live-mcp/plan.json').read_text(encoding='utf-8'))
    assert builder.sha(script) == plan['script_sha256'], 'Re-review script drift before effects'
    allocation = HERE/'live-allocation.json'
    assert not allocation.exists(), 'One run only; preserve antecedents, no automatic replay'
    before = payload(ready)
    sources = builder.pins()
    root = Path(tempfile.mkdtemp(prefix='nexus-hst-live-mcp-')).resolve()
    allocation.write_text(json.dumps(dict(root=str(root)), indent=2)+'\n', encoding='utf-8')
    (root/'cwd').mkdir()
    env = builder.environment(root)
    env['PATH'] = ''
    code = '''import importlib,importlib.metadata,json,pathlib,runpy,sys
prefix=pathlib.Path(sys.prefix).resolve()
origins={n:importlib.import_module(n).__file__ for n in ('okto_nexus','nexus_connector_core','okto_nexus_connector')}
assert sys.flags.isolated and sys.dont_write_bytecode
assert all(pathlib.Path(p).resolve().is_relative_to(prefix) for p in origins.values()), origins
assert importlib.metadata.version('okto-nexus')=='0.3.7'
pathlib.Path(sys.argv[2]).write_text(json.dumps(dict(origins=origins,prefix=str(prefix),sys_path=sys.path,isolated=True,dont_write_bytecode=True),indent=2),encoding='utf-8')
runpy.run_path(sys.argv[1],run_name='__main__')
'''
    argv = ['rtk', 'proxy', ready['python'], '-I', '-B', '-c', code, str(script), str(root/'origins.json')]
    report = dict(started_at=datetime.now(timezone.utc).isoformat(), root=str(root),
        argv=argv, cwd=str(root/'cwd'), script_sha256=builder.sha(script),
        wheel_sha256=ready['wheel_sha256'], provider_calls=0, real_harnesses=False)
    (root/'payload-before.json').write_text(json.dumps(before, indent=2)+'\n')
    with (root/'stdout.log').open('w', encoding='utf-8') as log:
        report['process'] = run_owned(argv, root=root, cwd=root/'cwd', env=env, log=log, timeout=180)
    output = (root/'stdout.log').read_text(encoding='utf-8')
    summary = None
    decoder = json.JSONDecoder()
    for index, char in enumerate(output):
        if char == '{':
            try:
                value, _ = decoder.raw_decode(output[index:])
                if isinstance(value, dict) and 'cleanup' in value and 'transport' in value:
                    summary = value
            except ValueError:
                pass
    report['summary'] = summary
    cleanup = (summary or {}).get('cleanup', {})
    after = payload(ready)
    end_sources = builder.pins()
    report.update(ended_at=datetime.now(timezone.utc).isoformat(),
        payload_files=len(after), payload_drift=before != after,
        source_drift=sorted(p for p in sources.keys() | end_sources.keys() if sources.get(p) != end_sources.get(p)),
        banner_pass='LIVE E2E RESULT: PASS' in output,
        cleanup_verified=cleanup.get('physical_exit') is True and cleanup.get('exit_code') == 0
            and cleanup.get('canonical_stop_exit_code') == 0)
    report['status'] = 'PASS' if (report['process']['success'] and report['banner_pass']
        and report['cleanup_verified'] and not report['payload_drift'] and not report['source_drift']) else 'NOT_GREEN'
    (root/'payload-after.json').write_text(json.dumps(after, indent=2)+'\n')
    (HERE/'live-qualification.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(status=report['status'],root=str(root),summary=summary,process=report['process']), indent=2))
    raise SystemExit(0 if report['status'] == 'PASS' else 1)


if __name__ == '__main__':
    main()
