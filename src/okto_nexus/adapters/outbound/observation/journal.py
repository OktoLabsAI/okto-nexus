"""Bounded JSON checkpoints with lifetime exclusion and atomic publication.

The application owns semantic validation and must never supply credentials.
This adapter accepts generic JSON objects only. It never creates directories,
repairs a malformed checkpoint, resets state or removes its stable lock file.
An I/O failure after publication may require an explicit read to learn the state.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import stat
import tempfile

from ..service_manager.locking import ExclusiveFileLock, LockBusy


MAX_JOURNAL_BYTES = 64 * 1024
MAX_JOURNAL_DEPTH = 32
_REPARSE_POINT = 0x400


class ObservationJournalError(Exception):
    """A closed local error code; never a path, document or underlying OS text."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _fail(code):
    raise ObservationJournalError(code)


def _same_file(left, right):
    return (left.st_dev, left.st_ino) == (right.st_dev, right.st_ino)


def _regular(info):
    return (stat.S_ISREG(info.st_mode) and info.st_nlink == 1
            and not getattr(info, "st_file_attributes", 0) & _REPARSE_POINT)


def _check_json(value):
    if type(value) is not dict:
        _fail("JOURNAL_INVALID")
    pending, visited = [(value, 1)], 0
    while pending:
        item, depth = pending.pop()
        visited += 1
        if visited > MAX_JOURNAL_BYTES or depth > MAX_JOURNAL_DEPTH:
            _fail("JOURNAL_INVALID")
        kind = type(item)
        if kind in (dict, list):
            if len(item) > MAX_JOURNAL_BYTES or len(pending) + len(item) > MAX_JOURNAL_BYTES:
                _fail("JOURNAL_INVALID")
            if kind is dict:
                for key, child in item.items():
                    if type(key) is not str or len(key) > MAX_JOURNAL_BYTES:
                        _fail("JOURNAL_INVALID")
                    key.encode("utf-8")
                    pending.append((child, depth + 1))
            else:
                pending.extend((child, depth + 1) for child in item)
        elif kind is str:
            if len(item) > MAX_JOURNAL_BYTES:
                _fail("JOURNAL_INVALID")
            item.encode("utf-8")
        elif kind is float:
            if not math.isfinite(item):
                _fail("JOURNAL_INVALID")
        elif item is not None and kind not in (int, bool):
            _fail("JOURNAL_INVALID")


def _encode(value):
    try:
        _check_json(value)
        chunks, length = [], 0
        encoder = json.JSONEncoder(ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        for chunk in encoder.iterencode(value):
            encoded = chunk.encode("utf-8")
            length += len(encoded)
            if length > MAX_JOURNAL_BYTES:
                _fail("JOURNAL_INVALID")
            chunks.append(encoded)
        return b"".join(chunks)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise ObservationJournalError("JOURNAL_INVALID") from None


def _object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            _fail("JOURNAL_INVALID")
        value[key] = item
    return value


def _constant(_):
    _fail("JOURNAL_INVALID")


def _decode(raw):
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_object, parse_constant=_constant)
        _check_json(value)
        return value
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise ObservationJournalError("JOURNAL_INVALID") from None


class ObservationJournal:
    """Explicit absolute checkpoint path, held exclusively for one with block.

    read returns None only for absence. create alone creates a checkpoint;
    write requires a valid existing object. Both validate before staging bytes.
    Root depth is one, and every nested JSON value adds one level (maximum 32).
    """

    def __init__(self, path):
        try:
            self._path = Path(path)
            if not self._path.is_absolute() or not self._path.name or ".." in self._path.parts:
                _fail("JOURNAL_PATH_INVALID")
            if os.name == "nt" and (str(self._path).startswith(("\\\\?\\", "\\\\.\\"))
                    or any(":" in part or part.endswith((" ", ".")) for part in self._path.parts[1:])):
                _fail("JOURNAL_PATH_INVALID")
        except (TypeError, ValueError):
            raise ObservationJournalError("JOURNAL_PATH_INVALID") from None
        self._lock_path = self._path.with_name(self._path.name + ".lock")
        self._lock = ExclusiveFileLock(self._lock_path)
        self._active = False

    def __repr__(self):
        return "ObservationJournal()"

    def _parents(self):
        for parent in reversed(self._path.parents):
            info = parent.lstat()
            if (not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode)
                    or getattr(info, "st_file_attributes", 0) & _REPARSE_POINT):
                _fail("JOURNAL_PATH_INVALID")

    @staticmethod
    def _file(path):
        try:
            info = path.lstat()
        except FileNotFoundError:
            return None
        if not _regular(info):
            _fail("JOURNAL_PATH_INVALID")
        return info

    def _guard(self):
        if not self._active:
            _fail("JOURNAL_NOT_OPEN")
        self._parents()
        lock_info = self._file(self._lock_path)
        held_info = os.fstat(self._lock._fd)
        if lock_info is None or not _regular(held_info) or not _same_file(lock_info, held_info):
            _fail("JOURNAL_PATH_INVALID")

    def __enter__(self):
        if self._active:
            _fail("JOURNAL_BUSY")
        try:
            self._parents()
            self._file(self._path)
            self._file(self._lock_path)
            self._lock.acquire()
            self._active = True
            self._guard()
            return self
        except LockBusy:
            raise ObservationJournalError("JOURNAL_BUSY") from None
        except ObservationJournalError:
            if self._active:
                self.__exit__(None, None, None)
            raise
        except (OSError, ValueError):
            if self._active:
                self.__exit__(None, None, None)
            raise ObservationJournalError("JOURNAL_IO_ERROR") from None

    def __exit__(self, exc_type, exc_value, traceback):
        self._active = False
        try:
            self._lock.release()
        except OSError:
            if exc_type is None:
                raise ObservationJournalError("JOURNAL_IO_ERROR") from None
        return False

    def _read(self):
        self._guard()
        info = self._file(self._path)
        if info is None:
            return None, None
        if info.st_size > MAX_JOURNAL_BYTES:
            _fail("JOURNAL_INVALID")
        fd = os.open(self._path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                     | getattr(os, "O_BINARY", 0) | getattr(os, "O_NONBLOCK", 0))
        try:
            opened = os.fstat(fd)
            if not _regular(opened) or not _same_file(info, opened):
                _fail("JOURNAL_PATH_INVALID")
            raw = bytearray()
            while len(raw) <= MAX_JOURNAL_BYTES:
                chunk = os.read(fd, min(16384, MAX_JOURNAL_BYTES + 1 - len(raw)))
                if not chunk:
                    break
                raw.extend(chunk)
            current = self._file(self._path)
            finished = os.fstat(fd)
            if (current is None or not _same_file(opened, current)
                    or (opened.st_size, opened.st_mtime_ns) != (finished.st_size, finished.st_mtime_ns)):
                _fail("JOURNAL_PATH_INVALID")
        finally:
            os.close(fd)
        if len(raw) > MAX_JOURNAL_BYTES:
            _fail("JOURNAL_INVALID")
        return _decode(raw), current

    def read(self):
        try:
            return self._read()[0]
        except OSError:
            raise ObservationJournalError("JOURNAL_IO_ERROR") from None

    def create(self, value):
        self._publish(value, create=True)

    def write(self, value):
        self._publish(value, create=False)

    def _publish(self, value, *, create):
        temporary = None
        try:
            self._guard()
            encoded = _encode(value)
            if create:
                if self._file(self._path) is not None:
                    _fail("JOURNAL_EXISTS")
                previous = None
            else:
                _, previous = self._read()
                if previous is None:
                    _fail("JOURNAL_MISSING")
            fd, temporary = tempfile.mkstemp(prefix=".observation-journal-", dir=self._path.parent)
            try:
                if not _regular(os.fstat(fd)):
                    _fail("JOURNAL_PATH_INVALID")
                offset = 0
                while offset < len(encoded):
                    written = os.write(fd, encoded[offset:])
                    if written <= 0:
                        raise OSError
                    offset += written
                os.fsync(fd)
                staged = os.fstat(fd)
            finally:
                os.close(fd)
            self._guard()
            staged_path = self._file(Path(temporary))
            if (staged_path is None or not _same_file(staged, staged_path)
                    or (staged.st_size, staged.st_mtime_ns) != (staged_path.st_size, staged_path.st_mtime_ns)):
                _fail("JOURNAL_PATH_INVALID")
            current = self._file(self._path)
            if create:
                if current is not None:
                    _fail("JOURNAL_EXISTS")
                try:
                    if os.name == "nt":
                        # Windows rename fails if the destination exists.
                        os.rename(temporary, self._path)
                    else:
                        # POSIX rename replaces; link is the atomic no-clobber
                        # publication. Remove the temporary link immediately.
                        os.link(temporary, self._path, follow_symlinks=False)
                        os.unlink(temporary)
                except FileExistsError:
                    raise ObservationJournalError("JOURNAL_EXISTS") from None
            else:
                if (current is None or not _same_file(previous, current)
                        or (previous.st_size, previous.st_mtime_ns) != (current.st_size, current.st_mtime_ns)):
                    _fail("JOURNAL_PATH_INVALID")
                os.replace(temporary, self._path)
            temporary = None
            published = self._file(self._path)
            if published is None or not _same_file(staged, published):
                _fail("JOURNAL_PATH_INVALID")
            if os.name != "nt":
                directory = os.open(self._path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                                    | getattr(os, "O_NOFOLLOW", 0))
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
        except (OSError, ValueError):
            raise ObservationJournalError("JOURNAL_IO_ERROR") from None
        finally:
            if temporary is not None:
                try:
                    os.unlink(temporary)
                except FileNotFoundError:
                    pass
                except OSError:
                    # Never hide the original failure or remove any target.
                    pass
