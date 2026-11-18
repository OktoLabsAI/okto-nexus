"""Transform only an already allocated own fixture; canonical inputs, no SQL."""
import ast
import hashlib
from pathlib import Path
import tempfile

PUBLIC = '<img src=x onerror="globalThis.HST_BROWSER_PUBLIC_EXECUTED=true">'
PRIVATE_TOKEN = 'HST_BROWSER_PRIVATE_TOKEN'
PRIVATE_PROMPT = 'HST_BROWSER_PRIVATE_PROMPT_NOT_FOR_OVERVIEW'
LABEL = PUBLIC + '\x1b[31m Bearer ' + PRIVATE_TOKEN


def transform_text(raw):
    text = raw.decode('utf-8')

    def replace(old, new):
        nonlocal text
        assert text.count(old) == 1, old
        text = text.replace(old, new, 1)

    replace("        workers=['hst-a'", '''        def review_h03(flow,selection):
            write('h03-input.private.json',dict(label=selection['label']))
            try:
                review=flow.review(selection)
            except BaseException as error:
                write('h03-label-admission.json',dict(review_accepted=False,error_type=type(error).__name__,dom_exercised_at_review=False))
                raise
            write('h03-label-admission.json',dict(review_accepted=True,dom_exercised_at_review=False))
            return review
        workers=['hst-a' ''')
    # Restore exact worker syntax after inserting the helper; no worker identity change.
    text = text.replace("workers=['hst-a' ,", "workers=['hst-a',", 1)
    replace('review=flow.review(dict(', 'review=review_h03(flow,dict(')
    replace("label='HST Second Project' if mode=='scope_two' and index else 'HST Demo Project',",
            'label=' + repr(LABEL) + ',')
    replace("else 'HST safe fixture turn'", 'else ' + repr(PRIVATE_PROMPT))
    replace("            operations.append(dict(intent=intent,operation_id=resolution['operation_id'],scope=resolution['scope']))",
            "            operations.append(dict(intent=intent,operation_id=resolution['operation_id'],scope=resolution['scope']))\n"
            "            if intent=='turn.submit' and extra.get('text')==" + repr(PRIVATE_PROMPT) + ":\n"
            "                write('h03-prompt-issued-'+str(len(operations))+'.json',dict(operation_id=resolution['operation_id'],scope=resolution['scope'],canonical_submit_accepted=True))")
    ast.parse(text)
    return text


def transform(root, fixture, expected_sha256):
    root, fixture = Path(root).resolve(), Path(fixture).resolve()
    assert root.parent == Path(tempfile.gettempdir()).resolve()
    assert root.name.startswith('nexus-hst-browser-')
    assert fixture == root / 'fixture.py' and not fixture.is_symlink()
    raw = fixture.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == expected_sha256
    text = transform_text(raw)
    fixture.write_text(text, encoding='utf-8')
    return {'source_sha256': expected_sha256,
            'fixture_sha256': hashlib.sha256(fixture.read_bytes()).hexdigest(),
            'sql_authority_mutations': 0, 'canonical_label_input': True,
            'canonical_turn_submit_input': True}
