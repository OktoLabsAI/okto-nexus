"""Seal three installed diagnostic GETs without application imports or reruns."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    raw = HERE / 'candidate-r7-100-v2-diagnostics.json'
    data = json.loads(raw.read_text(encoding='utf-8'))
    launch = json.loads((HERE / 'profile-r7-launch.json').read_text(encoding='utf-8'))
    ready = json.loads((HERE.parent / 'package-hst-r7/READY.json').read_text(encoding='utf-8'))
    owned = launch['owned_command']
    assert owned['success'] and owned['exit_code'] == 0 and not owned['timed_out'] and not owned['force_used']
    assert not owned['remaining_known_processes'] and not owned['remaining_listeners'] and not launch['pins_drift']
    assert data['productive_drift'] == [] and not data['payload_drift'] and data['schema_unchanged']
    assert data['source_seed_unchanged'] and data['source_dataset_unchanged']
    assert data['source_commit'] == ready['source_commit'] and data['wheel_sha256'] == ready['wheel_sha256']
    assert data['payload_files'] == ready['payload_files']
    assert all(data[key]['http_status'] == 200 and data[key]['status'] == 'ready'
        for key in ('cprofile', 'sql_diagnostic', 'main_transport_diagnostic'))
    observed = data['result_attention_profile_observation']
    indexed = [row for row in observed if Path(row['file']).name == 'home_entries.py' and row['function'] == 'project']
    udf = [row for row in observed if row['function'] == 'result_attention']
    batches = [row for row in data['sql_diagnostic']['statements']
        if row['template'] and " SELECT 'work' AS section,item," in row['template']]
    assert len(indexed) == 1 and indexed[0]['calls'] == 925 and not udf
    assert len(batches) == 1 and 'home_result_attention_v1(item,' not in batches[0]['template']
    out = HERE / 'profile-r7-final'
    out.mkdir(exist_ok=False)
    (out / 'worker.log').write_bytes((Path(launch['own_driver']) / 'profile.log').read_bytes())
    report = {'status': 'DIAGNOSTIC_COMPLETE_NOT_P95', 'get_count': 3,
        'source_commit': data['source_commit'], 'wheel_sha256': data['wheel_sha256'],
        'payload_files': data['payload_files'], 'package_modules': data['package_modules'],
        'transport': data['transport'], 'dataset_sha256': data['dataset_sha256'], 'seed_db_sha256': data['seed_db_sha256'],
        'guarded_scope': 'Own pristine mixed100/1000activities/100000history clone, installed-I-B, controlled clock; no lifespan/provider/native process/TCP.',
        'first_get_ms': {'http': data['cprofile']['http_elapsed_ms'], 'service': data['cprofile']['service_ms'],
            'json_render': data['cprofile']['render_ms'],
            'outside_service_render': data['cprofile']['transport_routing_auth_outside_service_and_other_ms']},
        'service_top20': data['cprofile']['service_functions'][:20],
        'serialization_top20': data['cprofile']['serialization_functions'][:20],
        'result_attention_observation': {'functions': observed, 'index_project_calls': indexed[0]['calls'],
            'legacy_result_attention_udf_calls': 0, 'batch_template_sha256': batches[0]['template_sha256'],
            'scalar_result_lookup_in_batch': False, 'methods_monkeypatched': False},
        'sql_get_ms': {'http': data['sql_diagnostic']['http_elapsed_ms'],
            'execute': data['sql_diagnostic']['execute_ms'], 'fetch': data['sql_diagnostic']['fetch_ms']},
        'sql_top20': [{key: row[key] for key in ('template_sha256', 'calls', 'execute_ms', 'fetch_ms', 'explain_error')}
            for row in data['sql_diagnostic']['statements'][:20]],
        'transport_get_ms': data['main_transport_diagnostic']['http_elapsed_ms'],
        'transport_top20': data['main_transport_diagnostic']['functions'][:20],
        'raw_diagnostic': '../' + raw.name, 'owned_launch': '../profile-r7-launch.json',
        'cleanup': {'normal_exit': True, 'force': False, 'timeout': False, 'remaining_processes': [],
            'remaining_listeners': [], 'pins_drift': [], 'payload_productive_schema_seed_dataset_drift': False},
        'limits': ['Three separate GETs, no nested profiler; not p95 samples or an SLO approval.',
            'cProfile cumulative costs and SQL execute/fetch costs include overlapping UDF/projection work; do not add them.',
            'Cold first GET includes routing/auth/import initialization. Third main-loop profile contains service execution itself.',
            'SQL/EXPLAIN preserve original templates only, no bound parameters or expanded SQL. EXPLAIN overhead excluded from execute/fetch.',
            'R7 matrix remains FAIL: candidate five PASS/three FAIL at500ms; baseline two FAIL. DOM remains NOT_RUN.',
            'No source/schema/seed/TTL changes, provider/native authority claim, or attribution of all elapsed time to ASGI.',
            owned['observation_limit']]}
    (out / 'qualification.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    rows = ['# R7 installed diagnostic — not p95', '',
        'Three separate HTTP200/ready GETs on a pristine mixed100 seed clone. All owned processes exited normally with no immutability drift.', '',
        f"Fastpath observed: {indexed[0]['calls']} index projections; zero legacy result-attention UDF calls. "
        f"Batch template {batches[0]['template_sha256']} contains no correlated result-attention scalar lookup.", '',
        f"First GET: HTTP {report['first_get_ms']['http']:.3f}ms; service {report['first_get_ms']['service']:.3f}ms; "
        f"render {report['first_get_ms']['json_render']:.3f}ms; outside these scopes {report['first_get_ms']['outside_service_render']:.3f}ms. "
        'The last quantity is neither pure transport nor pure product cost.', '',
        f"SQL GET: HTTP {report['sql_get_ms']['http']:.3f}ms, execute {report['sql_get_ms']['execute']:.3f}ms, "
        f"fetch {report['sql_get_ms']['fetch']:.3f}ms. Third GET HTTP {report['transport_get_ms']:.3f}ms; its profile includes service execution.", '',
        '| Service function | Calls | Own ms | Cumulative ms |', '|---|---:|---:|---:|']
    for row in report['service_top20']:
        rows.append(f"| {Path(row['file']).name}:{row['line']} {row['function']} | {row['calls']} | {row['own_ms']:.3f} | {row['cumulative_ms']:.3f} |")
    rows += ['', '| SQL template SHA256 | Calls | Execute ms | Fetch ms |', '|---|---:|---:|---:|']
    for row in report['sql_top20']:
        rows.append(f"| {row['template_sha256']} | {row['calls']} | {row['execute_ms']:.3f} | {row['fetch_ms']:.3f} |")
    rows += ['', *report['limits'], '',
        'Remaining measured costs include the combined Work/Results relation, canonicalization/fingerprints and complete board/page reduction. '
        'The lookup fastpath is active; fallback is not the explanation for this cut. No isolated proposed change is claimed to reach500ms.', '']
    (out / 'report.md').write_text('\n'.join(rows), encoding='utf-8')
    files = list(out.iterdir()) + [raw, HERE / 'profile-r7-launch.json', HERE / 'profile-r7-worker.py',
        HERE / 'profile-r7-launch.py', HERE / 'prepare-profile-r7.py', Path(__file__)]
    manifest = {'files': [{'path': path.relative_to(HERE).as_posix(),
        'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'bytes': path.stat().st_size} for path in sorted(files)]}
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'qualification': str(out / 'qualification.json'),
        'sha256': hashlib.sha256((out / 'qualification.json').read_bytes()).hexdigest()}))


if __name__ == '__main__':
    main()
