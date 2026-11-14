"""Fingerprint compatibility and bounded reads of installed wheel payloads."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from okto_nexus import service_environment as subject


@pytest.fixture
def payload(tmp_path, monkeypatch):
    site = tmp_path / 'site'
    site.mkdir()
    distribution = SimpleNamespace(files=[], version='1.2.3')
    distribution.read_text = lambda name: None
    distribution.locate_file = lambda name: site / name
    monkeypatch.setattr(subject.metadata, 'distribution', lambda name: distribution)

    def populate(values):
        for name, data in values.items():
            path = site / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        distribution.files = list(reversed(values))
        return distribution, site
    return populate


def legacy_digest(values):
    digest = hashlib.sha256()
    for raw_name in sorted(values):
        name = raw_name.replace('\\', '/')
        if '__pycache__/' in name or name.endswith(('.pyc', '.pyo')):
            continue
        digest.update(name.encode('utf-8') + b'\0' + hashlib.sha256(values[raw_name]).digest())
    return digest.hexdigest()


def observe_reads(monkeypatch, site, *, short=False, fail_after=None):
    original = Path.open
    reads, closed = [], []

    class Reader:
        def __init__(self, path, stream):
            self.path, self.stream, self.calls = path, stream, 0

        def read(self, size):
            reads.append((self.path.relative_to(site).as_posix(), size))
            self.calls += 1
            if fail_after is not None and self.calls > fail_after:
                raise OSError('fixture interrupted read')
            return self.stream.read(min(size, 3) if short else size)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.stream.close()
            closed.append(self.path)

    def tracked(path, mode='r', *args, **kwargs):
        stream = original(path, mode, *args, **kwargs)
        return Reader(path, stream) if mode == 'rb' else stream
    monkeypatch.setattr(Path, 'open', tracked)
    return reads, closed


def test_same_fingerprint_for_all_payload_names_order_empty_and_chunk_boundaries(payload, monkeypatch):
    values = {'fixture_pkg/z.py': b'z' * (64 * 1024 + 17), 'fixture_pkg/\u00e1.py': b'unicode name',
        'fixture_pkg/empty.py': b'', 'fixture_pkg/__pycache__/skip.pyc': b'ignored cache',
        'fixture.dist-info/RECORD': b'metadata is still fingerprinted',
        '../Scripts/fixture-script.py': b'installed entrypoint still fingerprinted'}
    _, site = payload(values)
    reads, _ = observe_reads(monkeypatch, site)
    assert subject._distribution('fixture', 'fixture_pkg') == {'version': '1.2.3', 'digest': legacy_digest(values)}
    assert reads and all(0 < size <= 64 * 1024 for _, size in reads)
    assert not any('__pycache__' in name for name, _ in reads)


def test_short_read_does_not_mean_end_of_payload(payload, monkeypatch):
    values = {'fixture_pkg/main.py': b'payload beyond the first short read'}
    _, site = payload(values)
    reads, closed = observe_reads(monkeypatch, site, short=True)
    assert subject._distribution('fixture', 'fixture_pkg')['digest'] == legacy_digest(values)
    assert len(reads) > 2 and len(closed) == 1


@pytest.mark.parametrize('sizes,accepted', [([32], True), ([33], False), ([32, 32], True), ([32, 32, 1], False)])
def test_file_and_distribution_limits_include_one_byte_overflow(payload, monkeypatch, sizes, accepted):
    monkeypatch.setattr(subject, '_MAX_FILE_BYTES', 32)
    monkeypatch.setattr(subject, '_MAX_DISTRIBUTION_BYTES', 64)
    values = {f'fixture_pkg/file{i}.py': bytes([i]) * size for i, size in enumerate(sizes)}
    _, site = payload(values)
    reads, closed = observe_reads(monkeypatch, site)
    if accepted:
        assert subject._distribution('fixture', 'fixture_pkg')['digest'] == legacy_digest(values)
    else:
        with pytest.raises(ValueError, match='exceeded its byte budget'):
            subject._distribution('fixture', 'fixture_pkg')
    assert len(closed) == len(sizes)
    assert all(0 < size <= 33 for _, size in reads)


def test_real_limits_and_protocol_remain_unchanged():
    assert subject._MAX_FILE_BYTES == 64 * 1024 * 1024
    assert subject._MAX_DISTRIBUTION_BYTES == 256 * 1024 * 1024
    assert subject._MAX_FILES == 10000
    assert subject.UPGRADE_PROTOCOL == 2


def test_file_count_counts_ignored_cache_entries_before_any_read(payload, monkeypatch):
    distribution, _ = payload({'fixture_pkg/main.py': b'payload'})
    distribution.files += [f'fixture_pkg/__pycache__/file{i}.pyc' for i in range(10000)]
    monkeypatch.setattr(Path, 'open', lambda *args, **kwargs: pytest.fail('oversized manifest was read'))
    with pytest.raises(ValueError, match='could not be verified'):
        subject._distribution('fixture', 'fixture_pkg')


def test_payload_changed_same_size_changes_fingerprint(payload):
    distribution, site = payload({'fixture_pkg/main.py': b'abc'})
    first = subject._distribution('fixture', 'fixture_pkg')
    (site / distribution.files[0]).write_bytes(b'abd')
    assert subject._distribution('fixture', 'fixture_pkg')['digest'] != first['digest']


def test_io_failure_closes_stream_and_never_returns_partial_fingerprint(payload, monkeypatch):
    _, site = payload({'fixture_pkg/main.py': b'abcd'})
    _, closed = observe_reads(monkeypatch, site, short=True, fail_after=1)
    with pytest.raises(OSError, match='interrupted read'):
        subject._distribution('fixture', 'fixture_pkg')
    assert len(closed) == 1


def test_editable_or_missing_python_payload_still_refused(payload):
    distribution, _ = payload({'fixture_pkg/main.py': b'abc'})
    distribution.read_text = lambda name: json.dumps({'dir_info': {'editable': True}})
    with pytest.raises(ValueError, match='not an editable'):
        subject._distribution('fixture', 'fixture_pkg')
    distribution.read_text = lambda name: None
    distribution.files = ['fixture.dist-info/RECORD']
    with pytest.raises(ValueError, match='could not be verified'):
        subject._distribution('fixture', 'fixture_pkg')


@pytest.mark.parametrize('requirements', [[], ['okto-nexus-connector-core>=1.2.3'],
    ['okto-nexus-connector-core==1.2.4'], ['okto-nexus-connector-core==1.2.3'] * 2])
def test_exact_core_pin_remains_mandatory(monkeypatch, requirements):
    monkeypatch.setattr(subject, '_distribution', lambda *args: {'version': '1.2.3', 'digest': 'a' * 64})
    monkeypatch.setattr(subject.metadata, 'requires', lambda name: requirements)
    with pytest.raises(ValueError, match='exact pin'):
        subject.snapshot()


def test_probe_keeps_60_second_boundary(monkeypatch, tmp_path):
    executable = tmp_path / 'python.exe'
    executable.write_bytes(b'fixture')
    calls = []

    def run(*args, **kwargs):
        calls.append(kwargs['timeout'])
        raise subject.subprocess.TimeoutExpired('fixture', kwargs['timeout'])
    monkeypatch.setattr(subject.subprocess, 'run', run)
    with pytest.raises(subject.EnvironmentInspectionError):
        subject.probe(executable)
    assert calls == [60]
