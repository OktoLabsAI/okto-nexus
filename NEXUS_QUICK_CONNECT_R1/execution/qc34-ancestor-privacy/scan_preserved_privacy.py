"""Read the same preserved privacy case after all owned processes exited.

Never export SQL values, credential-bearing files or raw logging messages.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3

HERE = Path(__file__).resolve().parent
ROOT = Path(json.loads((HERE / 'routed-allocation.json').read_text())['root']).resolve()
result = json.loads((ROOT / 'separate-result.json').read_text())
assert all(not process['alive'] for case in result['cases'] for process in case['processes_after'])
assert result['payload_files'] == 1027 and result['payload_drift'] == result['repository_input_drift'] == []
cases = {path.resolve() for path in (ROOT / 'privacy-observed-focal/tmp').glob('pytest-of-*/pytest-*/test_d25*')}
assert len(cases) == 1
case = cases.pop()
assert case.is_relative_to(ROOT)
origin = 'https://fixture-private-user:PRIVATE@privacy.invalid/owner/privacy-project.git?token=PRIVATE#PRIVATE'
patterns = ['PRIVATE', origin, 'privacy.invalid', 'fixture-private-user']
input_config = (case / 'workspace/.git/config').resolve()
assert input_config.is_file() and origin.encode() in input_config.read_bytes()
log_path = case / 'quick-cli-home/logs/observed-local.log'
logs = log_path.read_text(encoding='utf-8')
assert 'QC34_SINK_BEFORE' in logs and 'QC34_SINK_AFTER' in logs
http_events = sum('httpx HTTP Request:' in line for line in logs.splitlines())
assert http_events > 0
assert not any(pattern in logs for pattern in patterns)
assert not (case / 'git-trace.log').exists() and not (case / 'git-trace2.jsonl').exists()
db = case / 'home/nexus.db'
assert db.is_file()
db_before = hashlib.sha256(db.read_bytes()).hexdigest()
tables, violations, text_cells, total_rows = [], [], 0, 0
connection = sqlite3.connect(db.as_uri() + '?mode=ro', uri=True)
try:
    connection.execute('PRAGMA query_only=ON')
    names = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    assert names
    for name in names:
        quoted = '"' + name.replace('"', '""') + '"'
        count = 0
        for row in connection.execute('SELECT * FROM ' + quoted):
            count += 1
            for value in row:
                if isinstance(value, str):
                    text_cells += 1
                    if any(pattern in value for pattern in patterns):
                        violations.append(dict(scope='sqlite', table=name, pattern_present=True))
                elif isinstance(value, bytes):
                    text_cells += 1
                    for encoding in ('utf-8', 'utf-16-le', 'utf-16-be'):
                        if any(pattern in value.decode(encoding, errors='ignore') for pattern in patterns):
                            violations.append(dict(scope='sqlite_blob', table=name, pattern_present=True))
        total_rows += count
        tables.append(dict(table=name, rows=count))
finally:
    connection.close()
assert hashlib.sha256(db.read_bytes()).hexdigest() == db_before
files, errors, exclusions, total_bytes = [], [], [], 0
for path in sorted(case.rglob('*')):
    if not path.is_file():
        continue
    if path.resolve() == input_config:
        exclusions.append(str(path.relative_to(case)))
        continue
    try:
        data = path.read_bytes()
    except OSError as error:
        errors.append(dict(path=str(path.relative_to(case)), error=type(error).__name__))
        continue
    total_bytes += len(data)
    for encoding in ('utf-8', 'utf-16-le', 'utf-16-be'):
        if any(pattern in data.decode(encoding, errors='ignore') for pattern in patterns):
            violations.append(dict(scope='file', path=str(path.relative_to(case)), pattern_present=True))
    files.append(dict(path=str(path.relative_to(case)), bytes=len(data), sha256=hashlib.sha256(data).hexdigest()))
assert len(exclusions) == 1 and Path(exclusions[0]) == Path('workspace/.git/config')
report = dict(at=datetime.now(timezone.utc).isoformat(), scope='READ_ONLY_POST_EXIT_SCAN_OF_SAME_PRESERVED_CASE',
    original_runtime_node_status='FAILED_PERMISSION_ERROR_DURING_LIVE_FILE_SCAN', original_global_status='NOT_GREEN',
    case_root=str(case), input_config_confirmed_contains_synthetic_origin=True,
    sink=dict(kind='real UTF-8 logging.FileHandler', namespaces=['root', 'okto_nexus', 'httpx'],
        level='DEBUG', before_marker=True, after_marker=True, httpx_request_events=http_events,
        bytes=log_path.stat().st_size, sha256=hashlib.sha256(log_path.read_bytes()).hexdigest(),
        filters_or_redaction_added=False, outbound_product_telemetry_enabled=False),
    runtime_prefix_assertions='Source and failure location prove stdout, four JSON outputs, plain resume, active-sink/no-secret/traces assertions completed before the later file-read error; this is not a pytest PASS.',
    sqlite=dict(table_count=len(tables), tables=tables, total_rows=total_rows, text_or_blob_cells=text_cells,
        connection_mode='mode=ro;query_only=ON', main_database_sha256_unchanged=True),
    files=dict(count=len(files), bytes=total_bytes, manifest=files, read_errors=errors, only_exclusions=exclusions),
    violations=violations, trace_files_absent=True,
    raw_credentials_or_rows_or_sink_messages_exported=False,
    limitations=['Post-exit persistence scan, not proof of all transient live database states.',
        'The enabled local logging channels were observed; outbound analytics/other external sinks were not enabled or qualified.',
        'The prior access violation is inconclusive and not attributed to timed traceback instrumentation.',
        'No application, provider, session, grant or new setup was run during this scan.'])
(HERE / 'post-exit-privacy-scan.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(dict(table_count=len(tables), total_rows=total_rows, text_cells=text_cells,
    file_count=len(files), read_errors=len(errors), violations=len(violations),
    active_httpx_events=http_events, runtime_node_pass=False, global_status='NOT_GREEN')))
assert not violations and not errors
