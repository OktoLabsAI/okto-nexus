"""Isolated filesystem/process proofs for the optional observation journal."""
import json
import math
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from okto_nexus.adapters.outbound.observation import journal as module
from okto_nexus.adapters.outbound.observation.journal import (
    MAX_JOURNAL_BYTES, ObservationJournal, ObservationJournalError,
)


def failure(code):
    return pytest.raises(ObservationJournalError, match="^" + code + "$")


def test_create_read_write_are_detached_and_require_explicit_lifetime(tmp_path):
    path = tmp_path / "checkpoint.json"
    journal = ObservationJournal(path)
    assert repr(journal) == "ObservationJournal()"
    for operation in (journal.read, lambda: journal.create({}), lambda: journal.write({})):
        with failure("JOURNAL_NOT_OPEN"):
            operation()
    original = {"revision": 1, "pending": {"sequence": 9}, "label": "ação"}
    with journal:
        assert journal.read() is None
        with failure("JOURNAL_MISSING"):
            journal.write(original)
        journal.create(original)
        read = journal.read()
        assert read == original
        read["pending"]["sequence"] = 99
        assert journal.read() == original
        journal.write(dict(original, revision=2))
        assert journal.read()["revision"] == 2
        assert path.stat().st_nlink == 1
        with failure("JOURNAL_EXISTS"):
            journal.create({"replace": True})
    assert path.with_name(path.name + ".lock").is_file()
    with failure("JOURNAL_NOT_OPEN"):
        journal.read()
    with journal:
        assert journal.read()["revision"] == 2


def test_real_subprocess_cannot_enter_held_writer_and_can_resume_after_release(tmp_path):
    path = tmp_path / "checkpoint.json"
    code = """
import sys
from okto_nexus.adapters.outbound.observation.journal import ObservationJournal, ObservationJournalError
try:
    with ObservationJournal(sys.argv[1]) as journal:
        value = journal.read()
        journal.write(dict(value, sequence=value['sequence']+1))
    print('written')
except ObservationJournalError as error:
    print(error.code)
"""
    with ObservationJournal(path) as journal:
        journal.create({"sequence": 1})
        guard_identity = path.with_name(path.name + ".lock").stat().st_ino
        blocked = subprocess.run([sys.executable, "-c", code, str(path)],
            capture_output=True, text=True, timeout=10)
        assert blocked.returncode == 0 and blocked.stdout.strip() == "JOURNAL_BUSY"
        assert not blocked.stderr
        assert journal.read() == {"sequence": 1}
        with failure("JOURNAL_BUSY"):
            with ObservationJournal(path):
                pytest.fail("A second writer entered")
    resumed = subprocess.run([sys.executable, "-c", code, str(path)],
        capture_output=True, text=True, timeout=10)
    assert resumed.returncode == 0 and resumed.stdout.strip() == "written"
    assert not resumed.stderr
    assert path.with_name(path.name + ".lock").stat().st_ino == guard_identity
    with ObservationJournal(path) as journal:
        assert journal.read() == {"sequence": 2}


def test_process_exit_releases_lock_without_removing_or_resetting_the_journal(tmp_path):
    path = tmp_path / "checkpoint.json"
    code = """
import os,sys
from okto_nexus.adapters.outbound.observation.journal import ObservationJournal
with ObservationJournal(sys.argv[1]) as journal:
    journal.create({'sequence':37})
    os._exit(0)
"""
    result = subprocess.run([sys.executable, "-c", code, str(path)],
        capture_output=True, text=True, timeout=10)
    assert result.returncode == 0 and not result.stderr
    with ObservationJournal(path) as journal:
        assert journal.read() == {"sequence": 37}


@pytest.mark.parametrize("stage", ["partial_write", "fsync", "replace"])
def test_failure_before_publication_preserves_old_checkpoint_and_removes_only_temp(tmp_path, monkeypatch, stage):
    path = tmp_path / "checkpoint.json"
    old = {"sequence": 3, "pending": "retained-intent"}
    with ObservationJournal(path) as journal:
        journal.create(old)
        original_bytes = path.read_bytes()
        with monkeypatch.context() as patch:
            if stage == "partial_write":
                original_write = module.os.write
                calls = []

                def partial(fd, data):
                    calls.append(True)
                    if len(calls) == 1:
                        return original_write(fd, data[:5])
                    raise OSError("PRIVATE_PATH_AND_CONTENT_MUST_NOT_ESCAPE")

                patch.setattr(module.os, "write", partial)
            else:
                def fail(*args, **kwargs):
                    raise OSError("PRIVATE_PATH_AND_CONTENT_MUST_NOT_ESCAPE")

                patch.setattr(module.os, stage, fail)
            with failure("JOURNAL_IO_ERROR") as error:
                journal.write({"sequence": 4, "pending": "new-intent"})
            assert "PRIVATE" not in repr(error.value)
            assert str(path) not in str(error.value)
        assert path.read_bytes() == original_bytes
        assert journal.read() == old
        assert not list(tmp_path.glob(".observation-journal-*"))
        journal.write({"sequence": 4})
        assert journal.read() == {"sequence": 4}


def test_create_is_atomic_no_clobber_even_if_another_file_appears_at_publication(tmp_path, monkeypatch):
    path = tmp_path / "checkpoint.json"
    primitive = "rename" if os.name == "nt" else "link"
    publish = getattr(module.os, primitive)

    def race(source, destination, *args, **kwargs):
        Path(destination).write_bytes(b"unrelated existing file")
        return publish(source, destination, *args, **kwargs)

    with ObservationJournal(path) as journal, monkeypatch.context() as patch:
        patch.setattr(module.os, primitive, race)
        with failure("JOURNAL_EXISTS"):
            journal.create({"sequence": 1})
    assert path.read_bytes() == b"unrelated existing file"
    assert not list(tmp_path.glob(".observation-journal-*"))


@pytest.mark.parametrize("raw", [b"", b'{"sequence":', b'{"x":1,"x":2}', b'{"nested":{"x":1,"x":2}}',
    b'{"x":NaN}', b'{"x":Infinity}', b'{"x":-Infinity}', b'{"x":1e999}', b"[]", b"null",
    b'{"x":"\xff"}', b'{"x":"\\ud800"}', b" " * (MAX_JOURNAL_BYTES + 1)],
    ids=["empty", "truncated", "duplicate", "nested_duplicate", "nan", "infinity", "negative_infinity",
         "overflow_float", "list_root", "null_root", "invalid_utf8", "surrogate", "oversized"])
def test_invalid_existing_document_is_never_reset_or_overwritten(tmp_path, raw):
    path = tmp_path / "checkpoint.json"
    path.write_bytes(raw)
    with ObservationJournal(path) as journal:
        with failure("JOURNAL_INVALID"):
            journal.read()
        with failure("JOURNAL_INVALID"):
            journal.write({"fresh": True})
        with failure("JOURNAL_EXISTS"):
            journal.create({"fresh": True})
    assert path.read_bytes() == raw
    assert not list(tmp_path.glob(".observation-journal-*"))


@pytest.mark.parametrize("value", [[], None, {1: "nonstring key"}, {"x": (1, 2)}, {"x": {1, 2}},
    {"x": b"bytes"}, {"x": math.nan}, {"x": math.inf}, {"x": "\ud800"}],
    ids=["list_root", "null_root", "integer_key", "tuple", "set", "bytes", "nan", "infinity", "surrogate"])
def test_writes_require_exact_json_types_without_modifying_existing_state(tmp_path, value):
    path = tmp_path / "checkpoint.json"
    with ObservationJournal(path) as journal:
        journal.create({"sequence": 1})
        before = path.read_bytes()
        with failure("JOURNAL_INVALID"):
            journal.write(value)
        assert path.read_bytes() == before


def nested(levels):
    value = {}
    for _ in range(levels - 1):
        value = {"next": value}
    return value


def test_json_depth_cycles_and_byte_limit_are_bounded_in_both_directions(tmp_path):
    path = tmp_path / "checkpoint.json"
    with ObservationJournal(path) as journal:
        journal.create(nested(32))
        assert journal.read() == nested(32)
        for invalid in (nested(33), {"x": "é" * (MAX_JOURNAL_BYTES // 2)}):
            with failure("JOURNAL_INVALID"):
                journal.write(invalid)
        cycle = {}
        cycle["self"] = cycle
        with failure("JOURNAL_INVALID"):
            journal.write(cycle)
        exact = {"x": "a" * (MAX_JOURNAL_BYTES - 8)}
        journal.write(exact)
        assert path.stat().st_size == MAX_JOURNAL_BYTES
        assert journal.read() == exact
    path.write_text(json.dumps(nested(33)), encoding="utf-8")
    with ObservationJournal(path) as journal, failure("JOURNAL_INVALID"):
        journal.read()


def test_absolute_existing_parent_required_and_failures_do_not_create_directories(tmp_path):
    with failure("JOURNAL_PATH_INVALID"):
        ObservationJournal("relative.json")
    missing = tmp_path / "absent" / "checkpoint.json"
    with failure("JOURNAL_IO_ERROR"):
        with ObservationJournal(missing):
            pass
    assert not missing.parent.exists()
    with failure("JOURNAL_PATH_INVALID"):
        with ObservationJournal(tmp_path):
            pass


@pytest.mark.parametrize("target", ["journal", "lock"])
def test_hardlinked_files_are_refused_without_touching_the_other_name(tmp_path, target):
    path = tmp_path / "checkpoint.json"
    guarded = path if target == "journal" else path.with_name(path.name + ".lock")
    original = tmp_path / "original.json"
    original.write_bytes(b'{"original":true}')
    os.link(original, guarded)
    with failure("JOURNAL_PATH_INVALID"):
        with ObservationJournal(path):
            pass
    assert original.read_bytes() == b'{"original":true}'
    assert guarded.stat().st_nlink == 2


@pytest.mark.parametrize("target", ["journal", "lock", "parent"])
def test_reparse_attributes_are_refused_even_when_underlying_type_is_regular(tmp_path, monkeypatch, target):
    path = tmp_path / "checkpoint.json"
    path.write_bytes(b"{}")
    lock = path.with_name(path.name + ".lock")
    lock.write_bytes(b"")
    guarded = {"journal": path, "lock": lock, "parent": tmp_path}[target]
    original_lstat = Path.lstat

    def reparse(current, *args, **kwargs):
        info = original_lstat(current, *args, **kwargs)
        if current == guarded:
            return SimpleNamespace(st_mode=info.st_mode, st_nlink=info.st_nlink,
                                   st_file_attributes=0x400)
        return info

    monkeypatch.setattr(Path, "lstat", reparse)
    with failure("JOURNAL_PATH_INVALID"):
        with ObservationJournal(path):
            pass
    assert path.read_bytes() == b"{}"


def test_symlink_checkpoint_or_parent_is_refused_when_platform_allows_links(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    (real / "checkpoint.json").write_bytes(b"{}")
    alias = tmp_path / "alias"
    try:
        alias.symlink_to(real, target_is_directory=True)
    except OSError:
        pytest.skip("This test account cannot create symbolic links")
    with failure("JOURNAL_PATH_INVALID"):
        with ObservationJournal(alias / "checkpoint.json"):
            pass
    link = tmp_path / "linked.json"
    link.symlink_to(real / "checkpoint.json")
    with failure("JOURNAL_PATH_INVALID"):
        with ObservationJournal(link):
            pass
