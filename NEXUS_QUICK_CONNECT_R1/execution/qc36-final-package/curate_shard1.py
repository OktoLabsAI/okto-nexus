"""Curate shard 1 only after its installed runner has physically completed."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    assert root.parent == Path('C:/Users/jpamb/AppData/Local/Temp').resolve()
    assert root.name.startswith('nexus-qc36-installed-')
    result = json.loads((root / 'result.json').read_text(encoding='utf-8'))
    out = HERE / 'installed-shard-1'
    out.mkdir(exist_ok=True)
    inventory = json.loads((root / 'reports/inventory.json').read_text(encoding='utf-8'))
    phases = [json.loads(line) for line in (root / 'reports/phases.jsonl').read_text(encoding='utf-8').splitlines()]
    # Read only the runner's own descendants and own-root process matches.
    pids = [int(row['pid']) for row in result['known_processes']]
    expression = ' OR '.join('ProcessId=' + str(pid) for pid in pids)
    own_root = str(root).replace("'", "''")
    ps = "$rows = @(Get-CimInstance Win32_Process -Filter \"" + expression + "\" | Select-Object ProcessId,CreationDate,ExecutablePath); $own = @(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and $_.CommandLine.Contains('" + own_root + "') -and $_.Name -match '^python(w)?[.]exe$' } | Select-Object ProcessId,CreationDate,ExecutablePath); @{known=$rows;own_root=$own} | ConvertTo-Json -Depth 4"
    probe = subprocess.run(['rtk', 'proxy', 'C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe', '-NoProfile', '-Command', ps], capture_output=True, text=True, timeout=20)
    assert probe.returncode == 0
    presence = json.loads(probe.stdout)
    assert not presence['known'] and not presence['own_root'], presence
    # No known own process can retain a TCP listener; independently query those IDs.
    tcp_ps = '$ids = @(' + ','.join(map(str, pids)) + '); @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.OwningProcess -in $ids } | Select-Object LocalAddress,LocalPort,OwningProcess) | ConvertTo-Json'
    tcp = subprocess.run(['rtk', 'proxy', 'C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe', '-NoProfile', '-Command', tcp_ps], capture_output=True, text=True, timeout=20)
    assert not tcp.stdout.strip()
    copied = json.loads((root / 'copied-tests.json').read_text())
    copied_after = {p.relative_to(root / 'tree').as_posix(): sha(p) for p in (root / 'tree/tests').rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc', '.pyo')}
    copied_normal = {name.replace('\\', '/'): value for name, value in copied.items()}
    assert copied_normal == copied_after
    for name in ['result.json', 'copied-tests.json', 'source-before.json', 'payload-before.json', 'payload-after.json']:
        shutil.copyfile(root / name, out / name)
    for name in ['origins-start.json', 'origins-end.json', 'collected.json', 'inventory.json']:
        shutil.copyfile(root / 'reports' / name, out / name)
    sanitized = []
    for row in phases:
        clean = {key: value for key, value in row.items() if key != 'longrepr'}
        if 'longrepr' in row:
            clean['longrepr_retained_temp_only'] = True
        sanitized.append(clean)
    (out / 'phases.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in sanitized), encoding='utf-8')
    tree = ET.parse(root / 'reports/tests.xml')
    nodes = list(tree.iter('testcase'))
    for node in tree.iter():
        if node.tag in {'failure', 'error', 'system-out', 'system-err'}:
            node.text = '[Raw diagnostic retained in owned Temp; metadata only exported.]'
            node.attrib.pop('message', None)
    tree.write(out / 'junit-sanitized.xml', encoding='utf-8', xml_declaration=True)
    counts = {'passed': 0, 'failed': 0, 'errors': 0, 'skipped': 0}
    for node in nodes:
        key = 'failed' if node.find('failure') is not None else 'errors' if node.find('error') is not None else 'skipped' if node.find('skipped') is not None else 'passed'
        counts[key] += 1
    report = {
        'at': datetime.now(timezone.utc).isoformat(), 'mode': 'STRICT_INSTALLED_SHARD_1_OF_2',
        'status': 'PASS' if result['exit_code'] == 0 and not result['payload_drift'] and not result['source_drift'] and not inventory['not_run'] else 'NOT_GREEN',
        'candidate_source': '9bc4034663ca63cfee43790b4bc03c38f8bdebcc', 'selection': '--tests tests/quick_connect --shard-count 2 --shard-index 1 --timeout 1800',
        'runtime_root': str(root), 'counts': counts, 'junit_cases': len(nodes), 'collected': len(inventory['collected']), 'finished': len(inventory['finished']), 'not_run': inventory['not_run'],
        'payload_files': result['payload_files'], 'payload_drift': result['payload_drift'], 'source_drift': result['source_drift'], 'copied_test_drift': [],
        'process_cleanup': {'known_and_own_root_python_absent': True, 'known_own_listeners_absent': True, 'presence_probe': presence, 'signals': result['signals']},
        'provider_calls': 0,
        'raw_stdout': {'path': str(root / 'reports/stdout.log'), 'sha256': sha(root / 'reports/stdout.log'), 'exported': False},
        'limits': ['Parent and loaded package origins are strictly installed. Child provenance must be assessed for any test launching nested app subprocesses; runner does not rewrite original child argv.', 'A 0.25-second descendant sampler cannot prove it observed every short-lived child. Final own-root/PID/listener checks complement it without making that claim.', 'SKIP and NOT_RUN remain distinct; no union with other shards is asserted here.']}
    (out / 'qualification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    manifest = [{'path': p.relative_to(out).as_posix(), 'sha256': sha(p), 'bytes': p.stat().st_size} for p in sorted(out.rglob('*')) if p.is_file() and p.name != 'manifest.json']
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(json.dumps({'status': report['status'], 'counts': counts, 'qualification_sha256': sha(out / 'qualification.json')}))


if __name__ == '__main__':
    main()
