"""Version 1 framed, fsynced runtime ingress segments; one exclusive writer.

All filesystem work happens outside SQLite UoWs. Quota exhaustion fails closed;
this implementation never deletes captured results to make room for new events.
"""
from dataclasses import asdict, replace
import json
import os
from pathlib import Path
import re
import stat
import struct
import threading
import uuid
import zlib

from ....domain.harness import HarnessEvent

_HEADER = struct.Struct(">4sII")
_MAGIC = b"NJR1"
_SEGMENT = re.compile(r"segment-([0-9]{8})\.bin\Z")
_SECRET_KEYS = {"authorization", "api_key", "apikey", "access_token", "refresh_token",
                "id_token", "password", "secret", "session_secret", "credential"}
_SECRET_TEXT = re.compile(r"(?:nxs_|nxsept_)[A-Za-z0-9_-]+|\bsk-[A-Za-z0-9_-]{12,}|\bBearer\s+[^\s\"']+", re.I)


def redact(value):
    if isinstance(value, dict):
        return {key: "[REDACTED]" if key.lower() in _SECRET_KEYS else redact(item)
                for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return _SECRET_TEXT.sub("[REDACTED]", value)
    return value


class FileRuntimeEventJournal:
    def __init__(self, home_dir, *, quota_bytes=64 * 1024 * 1024,
                 segment_bytes=4 * 1024 * 1024, max_record_bytes=1024 * 1024):
        self.root = Path(home_dir) / "runtime-journal-v1"
        self.quota, self.segment_bytes, self.max_record = quota_bytes, segment_bytes, max_record_bytes
        self._lock = threading.RLock()
        self._owner_file = None
        self._index = []
        self._sequences = {}
        self._total = 0
        self._healthy = False
        self.store_id = None
        self._segment_number = 1
        self._tail_repairs = 0

    @staticmethod
    def _regular(path):
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or getattr(info, "st_file_attributes", 0) & 0x400:
            raise OSError("Journal path must be a regular, unlinked, non-reparse file")
        return info

    def _open(self, path, flags):
        fd = os.open(path, flags | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0), 0o600)
        try:
            actual, expected = os.fstat(fd), self._regular(path)
            if (actual.st_ino, actual.st_dev) != (expected.st_ino, expected.st_dev):
                raise OSError("Journal file identity changed")
        except BaseException:
            os.close(fd)
            raise
        return fd

    def _sync_directory(self):
        if os.name == "posix":
            fd = os.open(self.root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(fd)
            finally:
                os.close(fd)

    def start(self, *, initial_sequences=None):
        with self._lock:
            if self._owner_file is not None:
                self.check_admission()
                return
            # Refuse path redirection at every existing component.
            for path in (self.root, *self.root.parents):
                if path.exists() and (path.is_symlink() or getattr(path.lstat(), "st_file_attributes", 0) & 0x400):
                    raise OSError("Journal directory cannot contain symlinks or reparse points")
            self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
            owner_fd = self._open(self.root / "writer.lock", os.O_CREAT | os.O_RDWR)
            owner = os.fdopen(owner_fd, "r+b", buffering=0)
            try:
                if os.name == "nt":
                    import msvcrt
                    if os.fstat(owner_fd).st_size == 0:
                        owner.write(b"\0")
                    owner.seek(0)
                    msvcrt.locking(owner_fd, msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(owner_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self._owner_file = owner
                identity = self.root / "store-id"
                if not identity.exists():
                    fd = self._open(identity, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                    with os.fdopen(fd, "wb") as stream:
                        stream.write(str(uuid.uuid4()).encode("ascii"))
                        stream.flush()
                        os.fsync(stream.fileno())
                    self._sync_directory()
                fd = self._open(identity, os.O_RDONLY)
                with os.fdopen(fd, "rb") as stream:
                    self.store_id = str(uuid.UUID(stream.read(128).decode("ascii")))
                self._index, self._sequences, self._total = [], {}, 0
                paths = sorted(path for path in self.root.iterdir() if _SEGMENT.fullmatch(path.name))
                for index, path in enumerate(paths):
                    if int(_SEGMENT.fullmatch(path.name)[1]) != index + 1:
                        raise OSError("Journal segment gap")
                    self._recover_segment(path, last=index == len(paths) - 1)
                self._segment_number = len(paths) or 1
                for session, sequence in (initial_sequences or {}).items():
                    self._sequences[session] = max(sequence, self._sequences.get(session, 0))
                self._healthy = True
                self.check_admission()
            except BaseException:
                owner.close()
                self._owner_file = None
                self._healthy = False
                raise

    def _recover_segment(self, path, *, last):
        fd = self._open(path, os.O_RDWR)
        with os.fdopen(fd, "r+b") as stream:
            while True:
                offset = stream.tell()
                header = stream.read(_HEADER.size)
                if not header:
                    break
                if len(header) < _HEADER.size:
                    self._repair_tail(stream, offset, last)
                    break
                magic, size, checksum = _HEADER.unpack(header)
                if magic != _MAGIC or size > self.max_record:
                    raise OSError("Journal frame header corrupted")
                body = stream.read(size)
                if len(body) < size:
                    self._repair_tail(stream, offset, last)
                    break
                record = self._decode(body, checksum)
                if record["ordinal"] != len(self._index) + 1:
                    raise OSError("Journal ordinal gap")
                event = record["event"]
                if event["sequence"] <= self._sequences.get(event["session_id"], 0):
                    raise OSError("Journal session sequence regression")
                self._sequences[event["session_id"]] = event["sequence"]
                self._index.append((path, offset))
            self._total += stream.seek(0, os.SEEK_END)

    def _repair_tail(self, stream, offset, last):
        if not last:
            raise OSError("Truncated interior journal segment")
        stream.truncate(offset)
        stream.flush()
        os.fsync(stream.fileno())
        self._tail_repairs += 1

    def _decode(self, body, checksum):
        if zlib.crc32(body) != checksum:
            raise OSError("Journal checksum mismatch")
        record = json.loads(body)
        if record["version"] != 1 or record["store_id"] != self.store_id:
            raise OSError("Journal version/store mismatch")
        return record

    def check_admission(self):
        if not self._healthy or self._owner_file is None:
            raise OSError("Runtime journal is unavailable; admission stopped")
        if self._total >= self.quota:
            raise OSError("Runtime journal quota exhausted; admission stopped")

    def append(self, event: HarnessEvent, *, connection_id=None):
        with self._lock:
            self.check_admission()
            captured = replace(event, event_id="hevt_" + uuid.uuid4().hex,
                sequence=self._sequences.get(event.session_id, 0) + 1, payload=redact(event.payload))
            record = {"version": 1, "redaction_version": 1, "store_id": self.store_id,
                      "ordinal": len(self._index) + 1, "connection_id": connection_id,
                      "event": asdict(captured)}
            body = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            if len(body) > self.max_record or self._total + len(body) + _HEADER.size > self.quota:
                self._healthy = False
                raise OSError("Runtime journal record/retention quota exceeded")
            frame = _HEADER.pack(_MAGIC, len(body), zlib.crc32(body)) + body
            path = self.root / f"segment-{self._segment_number:08}.bin"
            try:
                if path.exists() and path.stat().st_size + len(frame) > self.segment_bytes:
                    self._segment_number += 1
                    path = self.root / f"segment-{self._segment_number:08}.bin"
                new_file = not path.exists()
                fd = self._open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT)
                os.lseek(fd, 0, os.SEEK_END)
                with os.fdopen(fd, "ab") as stream:
                    offset = stream.tell()
                    stream.write(frame)
                    stream.flush()
                    os.fsync(stream.fileno())
                if new_file:
                    self._sync_directory()
            except BaseException:
                self._healthy = False
                raise
            self._index.append((path, offset))
            self._sequences[event.session_id] = captured.sequence
            self._total += len(frame)
            return record

    def read_after(self, ordinal, *, limit=16):
        with self._lock:
            if ordinal < 0 or limit < 1:
                raise ValueError("Invalid journal cursor or limit")
            if self._owner_file is None:
                raise OSError("Runtime journal has no owner")
            records = []
            for path, offset in self._index[ordinal:ordinal + min(limit, 16)]:
                fd = self._open(path, os.O_RDONLY)
                with os.fdopen(fd, "rb") as stream:
                    stream.seek(offset)
                    magic, size, checksum = _HEADER.unpack(stream.read(_HEADER.size))
                    if magic != _MAGIC or size > self.max_record:
                        raise OSError("Journal frame changed after capture")
                    records.append(self._decode(stream.read(size), checksum))
            return records

    @property
    def watermark(self):
        return len(self._index)

    def close(self):
        with self._lock:
            self._healthy = False
            if self._owner_file is not None:
                self._owner_file.close()
                self._owner_file = None
