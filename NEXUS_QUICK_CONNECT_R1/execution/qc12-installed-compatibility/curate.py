"""Curate immutable original installed cuts and explicit runner counterparts."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
ROOT = Path(json.loads((HERE / 'allocation.json').read_text())['root'])
PREFIX = Path(json.loads((HERE / 'package-ready.json').read_text())['prefix']).resolve()
OUT = HERE / 'evidence'
OUT.mkdir(exist_ok=False)


def one_cut(name, result_file):
    result = json.loads((ROOT / result_file).read_text())
    assert result['payload_files'] == 1027
    assert result['payload_drift'] == result['repository_input_drift'] == []
    shutil.copyfile(ROOT / result_file, OUT / result_file)
    counts = dict(tests=0, failures=0, errors=0, skipped=0)
    for case in result['cases']:
        assert not case['signals'] and all(not process['alive'] for process in case['processes_after'])
        label = case['label']
        (OUT / label).mkdir()
        for filename in ('junit.xml', 'origins.json', 'raw.log', 'reports.jsonl', 'runner.json', 'failed-call.json'):
            if (ROOT / label / filename).exists():
                shutil.copyfile(ROOT / label / filename, OUT / label / filename)
        origins = json.loads((ROOT / label / 'origins.json').read_text())
        assert all(Path(value).resolve().is_relative_to(PREFIX) for value in origins['origins'].values())
        for suite in ET.parse(ROOT / label / 'junit.xml').getroot().iter('testsuite'):
            for key in counts:
                counts[key] += int(suite.attrib.get(key, '0'))
    counts['passed'] = counts['tests'] - counts['failures'] - counts['errors'] - counts['skipped']
    return dict(name=name, counts=counts, cases=len(result['cases']),
        results_file=result_file, all_owned_processes_exited=True, signals=[],
        installed_payload_files=1027, installed_payload_drift=[], source_drift=[])


original = one_cut('Original complete quick_connect plus three legacy nodes', 'result.json')
git = one_cut('Git entire file with CWD and TMP non-overlapping', 'counterpart-git-result.json')
pty = one_cut('Non-TTY exclusion counterpart; not PTY qualification', 'counterpart-pty-result.json')
assert git['counts'] == dict(tests=43, failures=0, errors=0, skipped=0, passed=43)
assert pty['counts'] == dict(tests=5, failures=0, errors=0, skipped=5, passed=0)
pty_origins = json.loads((ROOT / 'counterpart-pty/origins.json').read_text())
assert pty_origins['stdin_isatty'] is False and pty_origins['stdin_mode'] == 'PIPE_closed'
for filename in ('source-pins.json', 'pytest.ini'):
    shutil.copyfile(ROOT / filename, OUT / filename)
report = dict(at=datetime.now(timezone.utc).isoformat(),
    status='COMPLETED_ORIGINAL_RUNNER_FAILURES_AND_SEPARATE_COUNTERPARTS',
    source_commit='fa031697b37a1b879d855f7858f01320addf0df7',
    wheel_sha256=json.loads((HERE / 'package-ready.json').read_text())['wheel_sha256'],
    prefix=str(PREFIX), owned_root=str(ROOT), qualification='STRICT_INSTALLED_APPLICATION_IMPORTS',
    original=original, git_counterpart=git, non_tty_counterpart=pty,
    all_owned_processes_exited=True, forced=False, provider_calls=0,
    interpretation=[
        'The original total remains unchanged; counterpart results are not unioned into an all-green original.',
        'Original Git budget test correctly rejected the fake binary located beneath the runner CWD. The runner violated the requested CWD/TMP sibling isolation.',
        'Original Windows DEVNULL/NUL reported stdin.isatty=True but had no usable input, causing three EOF prompt failures. This is not evidence of working PTY or a product regression.',
        'The entire Git file passed with CWD outside TMP and unchanged product/tests/wheel.',
        'Closed PIPE confirmed non-TTY and yielded five honest PTY exclusions, not five passes.',
        'Positive historical real-PTY evidence is separate and was not repeated.',
    ],
    isolation=dict(application_src_copied=False, checkout_src_on_child_path=False,
        all_three_module_origins_under_prefix=True, installed_payload_count=1027,
        installed_payload_matches_wheels_start_finish=True, original_prefix_0s9_untouched=True),
    prevention='Future scripted non-TTY runners must use a PIPE with closed writer, assert stdin.isatty=False, and keep CWD outside TMP; Windows NUL is insufficient.',
    limitations=['Synthetic setup/model/lifecycle fixtures are not real harness or account qualification.',
        'No installation, service, provider, Windows login/reboot/suspend or native campaign performed.',
        'Only sanitized reports/logs and metadata are curated; own temporary DBs stay outside the repository.'])
(HERE / 'qualification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
manifest = {p.relative_to(HERE).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
    for p in OUT.rglob('*') if p.is_file()}
manifest['qualification.json'] = hashlib.sha256((HERE / 'qualification.json').read_bytes()).hexdigest()
(HERE / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
print(json.dumps(dict(original=original['counts'], git=git['counts'], non_tty=pty['counts'],
    qualification_sha256=manifest['qualification.json'], cleanup='all owned physical exits; zero signals')))
