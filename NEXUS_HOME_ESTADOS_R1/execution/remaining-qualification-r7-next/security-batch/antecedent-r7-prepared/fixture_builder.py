"""Build a gated derivative in an already allocated, own Temp directory.

This file never allocates or starts a runtime. Originals stay byte-identical.
"""
import ast
import hashlib
from pathlib import Path
import shutil
import tempfile

HERE = Path(__file__).resolve().parent


def replace_once(text, old, new):
    assert text.count(old) == 1, 'Qualified fixture anchor drift'
    return text.replace(old, new, 1)


def build(root, fixture_source, expected_source_sha256, case):
    root = Path(root).resolve()
    assert root.parent == Path(tempfile.gettempdir()).resolve()
    assert root.name.startswith('nexus-hst-browser-') and case in {'S1', 'S2'}
    original = Path(fixture_source).read_bytes()
    assert hashlib.sha256(original).hexdigest() == expected_source_sha256
    text = original.decode('utf-8').replace('\r\n', '\n')
    text = replace_once(text, '        browser_ready=False\n', '''        from security_controls import SecurityControls
        security=SecurityControls(deps,controls,refs,write)
        browser_ready=False
''')
    text = replace_once(text, "          write('initial-board.json',public)", "          write('initial-board.json',public)\n          security.snapshot('before')")
    text = replace_once(text, 'end=time.monotonic()+300;', 'end=time.monotonic()+180;')
    if case == 'S2':
        text = replace_once(text, "        '--feature-hitl','true',", "        '--feature-hitl','true','--feature-observations','true',")
    markers = ['security-snapshot-before-get', 'security-snapshot-after-get', 'security-revoke-grant'] if case == 'S1' else [
        'security-obs-owner', 'security-obs-idle', 'security-obs-completion',
    ]
    text = replace_once(text, "['complete','verify','revoke-reader','partial-results','restore-results']:", repr(markers) + ':')
    hook = '''                    if name=='security-snapshot-before-get':security.snapshot('before-get')
                    if name=='security-snapshot-after-get':security.snapshot('after-get')
                    if name=='security-revoke-grant':security.revoke_first_session_grant()
                    if name=='security-obs-owner':security.prepare_observation_owner()
                    if name=='security-obs-idle':security.publish_observation(False)
                    if name=='security-obs-completion':security.publish_observation(True)
'''
    text = replace_once(text, "                    done.add(name);write('controls.json',dict(done=sorted(done)))", hook + "                    done.add(name);write('controls.json',dict(done=sorted(done)))")
    # Syntax validation only; this is not a fixture/runtime qualification.
    ast.parse(text)
    destination = root / 'fixture.py'
    assert destination.is_file() and not destination.is_symlink()
    destination.write_text(text, encoding='utf-8')
    helper = root / 'helpers/security_controls.py'
    assert not helper.exists()
    shutil.copyfile(HERE / 'security_controls.py', helper)
    return {
        'case': case, 'source_sha256': hashlib.sha256(original).hexdigest(),
        'fixture_sha256': hashlib.sha256(destination.read_bytes()).hexdigest(),
        'helper_sha256': hashlib.sha256(helper.read_bytes()).hexdigest(),
        'owner_deadline_seconds': 180, 'sql_authority_mutations': 0,
    }
