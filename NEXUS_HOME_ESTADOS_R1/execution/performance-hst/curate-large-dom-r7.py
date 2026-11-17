"""Curate the single completed DOM observation; never navigate or import app."""
import hashlib
import json
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent
ROOT = Path('C:/Users/jpamb/AppData/Local/Temp/nexus-hst-browser-large-dom-r7-9j3wtz1r')
OUT = HERE / 'large-dom-r7-final'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def main():
    assert not OUT.exists(), 'Preserve all prior cuts'
    public = json.loads((ROOT / 'http-ready.json').read_text())
    final_path = Path(public['public_ready_path']).parent / 'final.json'
    final = json.loads(final_path.read_text())
    supervisor = json.loads((ROOT / 'supervisor.json').read_text())
    physical = json.loads((ROOT / 'physical-final.json').read_text(encoding='utf-8-sig'))
    text = (ROOT / 'cli-measure.txt').read_text(encoding='utf-8')
    result = json.loads(text.split('### Result\n', 1)[1].split('\n### Ran', 1)[0].strip())
    assert result['status'] == 'SINGLE_LARGE_DOM_MEASUREMENT' and result['samples'] == 1 and not result['isP95']
    assert result['targetMs'] == 2000 and result['withinTarget'] is (result['useful']['at'] <= 2000)
    assert result['errors'] == [] and all(row['method'] == 'GET' for row in result['requests'])
    assert result['canonicalResponse']['status'] == 200 and result['canonicalResponse']['version'] == 2
    assert result['canonicalResponse']['inventory']['registered_harnesses']['value'] == 100
    assert result['useful']['projectValue'] == 'hst-perf'
    assert result['useful']['headers'] == ['Active', 'Needs you', 'Results']
    assert result['useful']['cards'] == result['canonicalResponse']['cards']
    assert all(label in result['useful']['summary'] for label in result['requiredSummaryLabels'])
    assert all(row['status'] == 200 and row['sha256'] == public['assets'][row['name']] for row in result['assets'])
    assert final['error'] is None and final['schema_unchanged'] and final['source_dataset_unchanged']
    assert not final['payload_drift'] and not final['productive_drift'] and not supervisor['pins_drift']
    owned = supervisor['owned_command']
    assert owned['success'] and owned['exit_code'] == 0 and not owned['timed_out'] and not owned['force_used']
    assert not owned['remaining_known_processes'] and not owned['remaining_listeners']
    assert not physical['own_remaining'] and not physical['listeners']
    writes = [row for row in final['http_requests'] if row['method'] != 'GET']
    assert [(row['method'], row['path'], row['status']) for row in writes] == [
        ('POST', '/api/v1/operator-auth/account', 200), ('POST', '/api/v1/operator-auth/login', 200)]
    original_manifest = Path('C:/Users/jpamb/AppData/Local/Temp/nexus-hst-performance-open-c7deab6559c14026bbedef93822237d9/dataset.json')
    assert sha(original_manifest) == public['dataset_sha256']
    OUT.mkdir()
    save(OUT / 'measurement.json', result)
    save(OUT / 'http-ready.public.json', {key: value for key, value in public.items()
        if key not in ('private_storage_path', 'public_ready_path')})
    for source, name in [(final_path, 'http-final.json'), (ROOT / 'supervisor.json', 'supervisor.json'),
        (ROOT / 'physical-final.json', 'physical-final.json'), (ROOT / 'large-dom.png', 'large-dom.png'),
        (ROOT / 'cli-open.txt', 'cli-open.txt'), (ROOT / 'cli-close.txt', 'cli-close.txt')]:
        shutil.copyfile(source, OUT / name)
    raw = [ROOT / name for name in ('cli-measure.txt', 'cli-storage.txt', 'cli-screenshot.txt', 'http.log', 'measurement.js')]
    save(OUT / 'raw-references.json', {'private_temp_only': [{'path': str(path), 'sha256': sha(path), 'bytes': path.stat().st_size} for path in raw],
        'private_storage_database_vault_not_copied': True,
        'note': 'Raw measurement log includes generated code/private Temp paths, not cookie/password bytes. Public JSON result is retained separately.'})
    qualification = {'status': 'PASS' if result['withinTarget'] else 'FAIL',
        'layer': 'Single real browser navigation over own loopback HTTP, installed R7; synthetic SQL workload',
        'samples': 1, 'is_p95': False, 'first_useful_dom_ms': result['useful']['at'], 'target_ms': 2000,
        'functional_oracle': 'PASS', 'source_commit': public['source_commit'], 'wheel_sha256': public['wheel_sha256'],
        'payload_files': public['payload_files'], 'workload': public['counts'],
        'clock': {'server': public['seed_clock'], 'browser': result['clockOverride'],
            'performance_now_timers_os_auth_expiry': 'Real/untouched; Date/Date.now only aligned to unchanged seed.'},
        'cache': 'New own browser profile; browser HTTP cache disabled. Bootstrap/auth and OS caches may be warm; no board preflight.',
        'method': 'MutationObserver timestamp measured from real navigationStart, then matched against first authorized v2 cards/project/headers/summary and served asset SHA.',
        'guard_results': {'pristine_seed_schema_and_volume_verified': True, 'dataset_manifest_unchanged': True,
            'schema_payload_productive_unchanged': True, 'source_helper_pins_unchanged': True,
            'installed_module_origin_guard_executed': True, 'zero_provider_or_native_process_calls': True,
            'observation_get_only': True, 'operator_setup': 'Canonical own account/login before measurement; no domain/grant writes.',
            'no_retry': True},
        'cleanup': {'normal_http_exit': True, 'normal_cli_close': True, 'force': False, 'timeout': False,
            'owned_remaining': [], 'listeners': [], 'physical_audit': 'physical-final.json'},
        'limits': ['N=1 is not a percentile or confidence interval. No SLO retry occurred.',
            'Not proof of native/provider/current authority or real harnesses; synthetic OPEN facts correctly show unconfirmed/unknown.',
            'Only the first matching v2 DOM timestamp/response is retained; no per-response v1/v2 timing series was exported.',
            'Additional board GETs are normal page refreshes, not additional navigation/SLO samples.',
            'No causal attribution of the2.726s observation to a specific request/negotiation/render phase.',
            'The independent R7 p95 matrix remains five candidate PASS/three FAIL; this DOM observation cannot repair that gate.',
            owned['observation_limit']]}
    save(OUT / 'qualification.json', qualification)
    lines = ['# R7 large first-useful DOM — single observation', '',
        f"**{qualification['status']}: {qualification['first_useful_dom_ms']:.3f}ms against2000ms.** One real navigation; no retry and no p95 claim.", '',
        'The100-connection/1000OPEN/100000-history pristine synthetic seed was served through the installed R7 application. '
        'Project, three columns,10first-page harness IDs/assignments, unknown/operational counters and JS/CSS hashes matched the canonical v2 response. '
        'No page error or productive request occurred. The screenshot shows the qualified synthetic unconfirmed state; it is not native readiness evidence.', '',
        'Date/Date.now alone were aligned to the original seed clock. Monotonic browser timing, timers, OS clock and canonical cookie expiry remained real. '
        'Browser cache was disabled in a new own profile; server/bootstrap/auth and OS caches may be warm.', '',
        'The own browser closed normally; the verified stop file shut down the HTTP owner normally. Productive/schema/payload/seed/helper guards passed. '
        'Final own-process/session and port scans found no remaining process/listener. Cookies/passwords/DB/vault stay private Temp.', '',
        *qualification['limits'], '', 'See measurement.json for the exact observed timestamp/canonical match and large-dom.png for visual inspection.', '']
    (OUT / 'report.md').write_text('\n'.join(lines), encoding='utf-8')
    paths = list(OUT.iterdir()) + [Path(__file__), HERE / 'large-dom-r7-launch.py', HERE / 'large-dom-r7-runbook.md',
        HERE / 'large-dom-http-prepared.py', HERE / 'large-dom-driver-prepared.js']
    save(OUT / 'manifest.json', {'files': [{'path': path.relative_to(HERE).as_posix(),
        'sha256': sha(path), 'bytes': path.stat().st_size} for path in sorted(paths)]})
    print(json.dumps({'qualification': str(OUT / 'qualification.json'), 'sha256': sha(OUT / 'qualification.json'),
        'screenshot': str(OUT / 'large-dom.png'), 'status': qualification['status']}))


if __name__ == '__main__':
    main()
