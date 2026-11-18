"""Static transform only; caller must gate, own and hash its Temp fixture first."""
import ast
import hashlib
from pathlib import Path
import tempfile

PUBLIC = '<img src=x onerror="globalThis.HST_BROWSER_PUBLIC_EXECUTED=true">'
PRIVATE_TOKEN = 'HST_BROWSER_PRIVATE_TOKEN'
PRIVATE_PROMPT = 'HST_BROWSER_PRIVATE_PROMPT_NOT_FOR_OVERVIEW'


def transform(root, fixture, expected_sha256):
    root, fixture = Path(root).resolve(), Path(fixture).resolve()
    assert root.parent == Path(tempfile.gettempdir()).resolve()
    assert root.name.startswith('nexus-hst-browser-')
    assert fixture == root / 'fixture.py' and fixture.is_file() and not fixture.is_symlink()
    raw = fixture.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == expected_sha256
    text = raw.decode('utf-8').replace('\r\n', '\n')
    old = "label='HST Second Project' if mode=='scope_two' and index else 'HST Demo Project',"
    label = PUBLIC + '\x1b[31m\nBearer ' + PRIVATE_TOKEN
    new = 'label=' + repr(label) + " if index==0 else 'HST Other Project',"
    assert text.count(old) == 1
    text = text.replace(old, new, 1)
    old = "else 'HST safe fixture turn'"
    assert text.count(old) == 1
    text = text.replace(old, 'else ' + repr(PRIVATE_PROMPT), 1)
    ast.parse(text)
    fixture.write_text(text, encoding='utf-8')
    return {'source_sha256': expected_sha256,
            'fixture_sha256': hashlib.sha256(fixture.read_bytes()).hexdigest(),
            'canonical_label_input': True, 'canonical_turn_submit_input': True,
            'sql_mutations': 0, 'authority_changes': 0}
