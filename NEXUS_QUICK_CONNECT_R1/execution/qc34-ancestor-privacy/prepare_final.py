import difflib
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
root = Path(tempfile.mkdtemp(prefix='nexus-qc34-private-final-')).resolve()
previous = Path(json.loads((HERE / 'routed-allocation.json').read_text())['root'])
shutil.copytree(previous / 'after', root / 'after', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
shutil.copyfile(previous / 'pytest.ini', root / 'pytest.ini')
pins = {str(p.relative_to(REPO)): hashlib.sha256(p.read_bytes()).hexdigest() for p in (REPO / 'src').rglob('*') if p.is_file() and '__pycache__' not in p.parts}
(root / 'source-pins.json').write_text(json.dumps(pins, indent=2))
test = root / 'after/tests/quick_connect/test_ancestor_privacy.py'
before = test.read_text()
after = before.replace('import logging\n', 'import logging\nimport os\nimport stat\n')
old = '''        data = path.read_bytes()
        total_bytes += len(data)'''
new = '''        def facts(p):
            s = p.lstat()
            return {'size': s.st_size, 'device': s.st_dev, 'inode': s.st_ino,
                'mode': s.st_mode, 'attributes': getattr(s, 'st_file_attributes', 0)}
        prior = facts(path)
        attempt = {'path': str(path.relative_to(tmp_path)), 'before': prior}
        with audit.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps({'phase': 'before_read', **attempt}) + '\\n')
        try:
            data = path.read_bytes()
        except PermissionError:
            later = facts(path)
            assert path.resolve() == expected_lock
            assert stat.S_ISREG(prior['mode']) and not prior['attributes'] & 0x400
            assert prior == later and prior['size'] == 1
            assert prior['size'] < min(map(len, encoded))
            assert type(journal) is event_journal.FileRuntimeEventJournal
            assert journal.root.resolve() / 'writer.lock' == expected_lock
            owner = journal._owner_file
            assert owner is not None and not owner.closed
            owner_stat = os.fstat(owner.fileno())
            assert (owner_stat.st_dev, owner_stat.st_ino, owner_stat.st_size) == (prior['device'], prior['inode'], 1)
            assert hashlib.sha256(producer.read_bytes()).hexdigest() == producer_sha
            proof = {**attempt, 'after': later, 'outcome': 'length_proof',
                'minimum_marker_encoded_bytes': min(map(len, encoded)),
                'producer': str(producer), 'producer_sha256': producer_sha,
                'same_live_owner_identity': True}
            length_proofs.append(proof)
            with audit.open('a', encoding='utf-8') as stream:
                stream.write(json.dumps({'phase': 'after_read', **proof}) + '\\n')
            continue
        with audit.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps({'phase': 'after_read', **attempt, 'outcome': 'full_read', 'bytes_read': len(data)}) + '\\n')
        total_bytes += len(data)'''
assert old in after
after = after.replace(old, new)
old = '    files, total_bytes, exclusions = [], 0, []\n'
new = '''    from okto_nexus.adapters.outbound.harness import event_journal
    producer = Path(event_journal.__file__).resolve()
    producer_sha = hashlib.sha256(producer.read_bytes()).hexdigest()
    assert producer_sha == PRODUCER_SHA
    journal = c.t.deps.harness_supervisor.event_ingress.journal
    expected_lock = (Path(c.t.deps.config.home_dir) / 'runtime-journal-v1/writer.lock').resolve()
    assert expected_lock.is_relative_to(tmp_path.resolve())
    audit = Path(os.environ['QC_DERIVATIVE_OUTPUT']) / 'file-read-audit.jsonl'
    length_proofs = []
    files, total_bytes, exclusions = [], 0, []
'''
package = Path(json.loads((HERE.parent / 'qc11-package/allocation.json').read_text())['root'])
producer_sha = hashlib.sha256((package / 'venv/Lib/site-packages/okto_nexus/adapters/outbound/harness/event_journal.py').read_bytes()).hexdigest()
new = new.replace('PRODUCER_SHA', repr(producer_sha))
assert old in after
after = after.replace(old, new)
after = after.replace("no_secret(value if isinstance(value, str) else value.decode('utf-8', errors='ignore'))", "\n                        if isinstance(value, str):\n                            no_secret(value)\n                        else:\n                            assert not any(pattern in value for pattern in encoded)\n                            for encoding in ('utf-8', 'utf-16-le', 'utf-16-be'):\n                                no_secret(value.decode(encoding, errors='ignore'))")
after = after.replace("'files': files, 'file_bytes_checked'", "'length_proofs': length_proofs, 'producer_sha256': producer_sha, 'files': files, 'file_bytes_checked'")
test.write_text(after, encoding='utf-8', newline='\n')
(root / 'changes.patch').write_text(''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True), fromfile='routed/test_ancestor_privacy.py', tofile='final/test_ancestor_privacy.py')))
(HERE / 'final-allocation.json').write_text(json.dumps({'root': str(root)}, indent=2))
runner = (HERE / 'run_routed.py').read_text().replace("HERE/'routed-allocation.json'", "HERE/'final-allocation.json'")
start = runner.index('nodes=[')
end = runner.index('\nfor label,node in nodes:', start)
runner = runner[:start] + "nodes=[('final-private-focal','tests/quick_connect/test_ancestor_privacy.py::test_d25_private_origin_does_not_enter_observed_logs_json_homes_or_sqlite')]" + runner[end:]
(HERE / 'run_final.py').write_text(runner)
print(json.dumps({'root': str(root), 'test_sha256': hashlib.sha256(test.read_bytes()).hexdigest(), 'producer_sha256': producer_sha}))
