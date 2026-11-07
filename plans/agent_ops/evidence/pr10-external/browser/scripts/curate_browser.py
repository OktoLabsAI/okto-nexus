"""Retain explicit synthetic browser evidence; never archive private credentials."""
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

ROOT = Path(__file__).resolve().parent
QUALIFIED = ROOT / 'qualified'
REPO = Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
DEST = REPO / 'plans/agent_ops/evidence/pr10-external/browser'
DEST.mkdir(parents=True, exist_ok=False)
private_values = [row['token'].encode() for row in json.loads(
    (QUALIFIED / 'browser-fixture-private.json').read_text(encoding='utf-8')).values()]
retained = []


def checked_bytes(path):
    data = path.read_bytes()
    assert not any(value in data for value in private_values), 'Private credential found; no archive written.'
    return data


def retain(path, relative):
    data = checked_bytes(path)
    target = DEST / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    assert not target.exists()
    target.write_bytes(data)
    retained.append(dict(source=str(path), path=relative, bytes=len(data),
                         sha256=hashlib.sha256(data).hexdigest()))


for name in ('browser-fixture-metadata.json', 'browser-canonical-before.json',
             'browser-server-proof.json', 'server-import-proof.json', 'server-cleanup.json'):
    retain(QUALIFIED / name, name)
for name in ('server_entry.py', 'start_server.py', 'browser_fixture.py', 'stop_server.py', 'curate_browser.py'):
    retain(ROOT / name, 'scripts/' + name)
for path in sorted((REPO / 'output/playwright').glob('pr10-external-*')):
    assert path.suffix in ('.yml', '.png')
    retain(path, 'ui/' + path.name)
for name in ('page-2026-11-07T02-44-05-482Z.yml', 'page-2026-11-07T02-44-38-629Z.yml',
             'page-2026-11-07T02-46-12-560Z.yml', 'page-2026-11-07T02-46-53-065Z.yml',
             'page-2026-11-07T02-48-35-077Z.yml', 'page-2026-11-07T03-02-56-954Z.yml',
             'console-2026-11-07T02-36-18-282Z.log'):
    retain(REPO / '.playwright-cli' / name, 'ui/' + name)

trace_root = REPO / '.playwright-cli/traces'
stem = 'trace-1794019020953'
trace_files = {stem + suffix for suffix in ('.trace', '.network', '.stacks')}
for suffix in ('.trace', '.network'):
    for line in checked_bytes(trace_root / (stem + suffix)).decode('utf-8').splitlines():
        stack = [json.loads(line)]
        while stack:
            value = stack.pop()
            if isinstance(value, dict):
                for key, item in value.items():
                    if key in ('file', '_file') and isinstance(item, str) and item.startswith(('resources/', 'screencast/')):
                        trace_files.add(item)
                    if isinstance(item, (dict, list)):
                        stack.append(item)
            elif isinstance(value, list):
                stack.extend(value)
trace_entries = []
archive = DEST / 'playwright-trace.zip'
with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as output:
    for name in sorted(trace_files):
        source = (trace_root / name).resolve()
        assert source.is_relative_to(trace_root.resolve())
        data = checked_bytes(source)
        output.writestr(name, data)
        trace_entries.append(dict(path=name, bytes=len(data), sha256=hashlib.sha256(data).hexdigest()))
with zipfile.ZipFile(archive) as check:
    assert check.testzip() is None
    assert set(check.namelist()) == trace_files
    for entry in trace_entries:
        assert hashlib.sha256(check.read(entry['path'])).hexdigest() == entry['sha256']
retained.append(dict(source='Explicit referenced trace files only', path=archive.name,
                     bytes=archive.stat().st_size, sha256=hashlib.sha256(archive.read_bytes()).hexdigest()))


def snapshot(name):
    return (DEST / 'ui' / name).read_text(encoding='utf-8')


assert 'matching items · 4 shown' in snapshot('page-2026-11-07T02-44-05-482Z.yml')
assert 'matching items · 3 shown' in snapshot('pr10-external-one-completion-seen.yml')
assert 'External activity for pr10-observed-b' in snapshot('pr10-external-workspace-b.yml')
assert 'External activity for pr10-observed-a' not in snapshot('pr10-external-workspace-b.yml')
assert '1 working; 1 awaiting input; 3 activity unknown (2 expired; 1 without a report)' in snapshot('pr10-external-ttl-instance.yml')
assert 'no longer matches the selected generation and scope' in snapshot('pr10-external-generation-fence.yml')
assert 'snapshot out of date' in snapshot('pr10-external-before-read-failure.yml')
assert 'External activity for' not in snapshot('pr10-external-summary-403.yml')
assert 'Protected observations have been cleared' in snapshot('pr10-external-summary-403.yml')
assert 'matching items · 0 shown' in snapshot('pr10-external-off-attention-final.yml')
assert '5 activity unknown (5 unavailable)' in snapshot('pr10-external-off-agents-final.yml')
proof = json.loads((DEST / 'browser-server-proof.json').read_text(encoding='utf-8'))
assert proof['unchanged'] and not proof['changed'] and proof['tables'] == 146
cleanup = json.loads((DEST / 'server-cleanup.json').read_text(encoding='utf-8'))
assert cleanup['process_wait_code'] == 0 and cleanup['tcp_connect_code'] != 0
assert cleanup['shutdown']['data']['shutdown']['state'] == 'DRAINED'

result = dict(
    candidate='Initial installed PR10a wheel before backend performance optimization',
    wheel_sha256='48eee2b5136f40ed3f37e4df73896d8d4d91bbc064d2cf918d2dfa85c461292d',
    platform='Windows; real Chrome 156; Playwright CLI 0.1.23 / engine 1.65.0-alpha-2026-10-30',
    peers='Synthetic identities and reports only; actual loopback HTTP, SQLite and installed packages',
    checks={
        'attention_four_watch_zero_action': True,
        'external_blocked_inspection_has_no_approval_or_execution': True,
        'malicious_text_escaped_no_js_execution_or_link': True,
        'completion_retained_separately_when_new_head_working': True,
        'seen_dismisses_only_one_of_two_completion_episodes': True,
        'agent_counts_and_workspace_scope': True,
        'expired_report_activity_unknown_not_idle': True,
        'generation_change_clears_selected_inspection': True,
        'injected_network_failure_marks_snapshot_stale_and_recovers': True,
        'injected_403_clears_protected_observations_until_remount': True,
        'feature_off_zero_attention_unavailable_agent_counts_then_on_recovers': True,
        'escape_closes_inspection_and_restores_trigger_focus': True,
        'light_and_dark_narrow_visual_review': True,
        'dark_620px_document_and_external_sections_no_horizontal_overflow': True,
        'canonical_146_tables_unchanged': True,
        'canonical_server_stop_exact_process_handle_and_tcp_closed': True,
    },
    limits=[
        'No real provider, external client, native user service, or OBS12 correlation acceptance.',
        'Network abort and 403 are explicit browser-route injections; other state transitions used real HTTP.',
        'First feature-off snapshots retained the prior 403 blocked client state; only off-*-final snapshots qualify feature-off rendering.',
        'Initial click was intercepted by the default metrics notice; it was dismissed without enabling metrics.',
        'An initial diagnostic queried role=dialog instead of the native dialog element and failed; the corrected diagnostic is retained in the trace.',
        'One navigation ref became stale after a badge update; a fresh snapshot was used.',
        'Tab focus diagnostic across separate commands was inconclusive; only Escape/trigger focus is claimed.',
        'Current final private publisher values were scanned without retaining their values or hashing the private file. Initial bearers never entered the browser; trace HTTP request headers contain no authorization credentials.',
    ],
    retained_inputs=retained, trace_entries=trace_entries,
)
(DEST / 'browser-results.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(dict(files=len(retained) + 1, trace_entries=len(trace_entries),
                     bytes=sum(item['bytes'] for item in retained), destination=str(DEST)), indent=2))
