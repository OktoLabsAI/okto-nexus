"""Bounded coded lifecycle diagnostics; no provider text or runtime authority."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import re
import stat

from ....errors import ErrorCode

LOG_NAME = 'service.jsonl'
MAX_READ = 256 * 1024
MAX_RECORD = 2048
_CODES = {'STARTING', 'BOOTSTRAP_FAILED', 'READY_FOR_QUERIES',
          'SHUTDOWN_REPORTED', 'EXIT_FAILED', 'SERVICE_EXIT'}
_STATES = {'STARTING', 'READY', 'RUNNING', 'DRAINING', 'DRAINING_PENDING', 'DRAINED',
           'RECOVERY_REQUIRED', 'UNCONFIRMED'}
_SUPERVISORS = {'foreground', 'detached', 'windows-task-scheduler'}
_FIELDS = {'timestamp', 'component', 'code', 'generation', 'supervisor', 'state', 'error_code'}


def _safe_record(value):
    if (not isinstance(value, dict) or set(value) != _FIELDS
            or value.get('component') != 'server' or value.get('code') not in _CODES
            or value.get('supervisor') not in _SUPERVISORS
            or value.get('state') not in _STATES
            or value.get('error_code') not in {None, *(code.value for code in ErrorCode)}
            or not isinstance(value.get('generation'), str)
            or re.fullmatch('[0-9a-f]{32}', value['generation']) is None
            or not isinstance(value.get('timestamp'), str)
            or re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+00:00', value['timestamp']) is None):
        return None
    return value


def _regular(path):
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
            or getattr(info, 'st_file_attributes', 0) & 0x400):
        raise OSError('The selected log is not a regular private file')
    return info


def _directory(home):
    directory = Path(home) / 'logs'
    if directory.exists() and (directory.is_symlink()
            or getattr(directory.lstat(), 'st_file_attributes', 0) & 0x400):
        raise OSError('The log directory is redirected')
    return directory


class _Handler(RotatingFileHandler):
    def handleError(self, record):
        # Logging failure must neither expose a traceback nor change admission.
        self.failed = True


class ServiceLog:
    """Created only by the runtime after acquiring instance ownership."""
    def __init__(self, home, *, generation, supervisor, max_bytes=2 * 1024 * 1024):
        self.generation, self.supervisor = generation, supervisor
        directory = _directory(home)
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        path = directory / LOG_NAME
        if path.exists():
            _regular(path)
        self.handler = _Handler(path, maxBytes=max_bytes, backupCount=3, encoding='utf-8')
        self.handler.setFormatter(logging.Formatter('%(message)s'))
        self.handler.failed = False
        self.closed = False

    def write(self, code, *, state='UNCONFIRMED', error_code=None):
        value = _safe_record({'timestamp': datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'component': 'server', 'code': code, 'generation': self.generation,
            'supervisor': self.supervisor, 'state': state if state in _STATES else 'UNCONFIRMED',
            'error_code': error_code if isinstance(error_code, str)
                and error_code in {item.value for item in ErrorCode} else None})
        if value is None:
            return
        with self.handler.lock:
            if not self.closed:
                self.handler.handle(logging.LogRecord('okto_nexus.service', logging.INFO,
                    '', 0, json.dumps(value, separators=(',', ':')), (), None))

    def close(self):
        with self.handler.lock:
            self.closed = True
            try:
                self.handler.close()
            except OSError:
                self.handler.failed = True


@dataclass(frozen=True)
class LogCursor:
    identity: tuple[int, int]
    offset: int
    pending: bytes = b''


def read_logs(home, *, tail=50, cursor=None):
    """Read one bounded snapshot; close all handles before the next follow poll."""
    if type(tail) is not int or not 1 <= tail <= 10000:
        raise ValueError('tail must be between 1 and 10000')
    result = {'component': 'server', 'kind': 'service_logs', 'state': 'available',
              'service_state': 'not_checked', 'work_state': 'not_checked',
              'events': [], 'truncated': False, 'rotated': False,
              'discarded_records': 0, 'reason': None}
    try:
        path = _directory(home) / LOG_NAME
        expected = _regular(path)
        with path.open('rb') as stream:
            info = os.fstat(stream.fileno())
            identity = (info.st_dev, info.st_ino)
            if identity != (expected.st_dev, expected.st_ino):
                raise OSError('Log changed during observation')
            same = cursor is not None and cursor.identity == identity and info.st_size >= cursor.offset
            result['rotated'] = cursor is not None and not same
            offset = cursor.offset if same else max(0, info.st_size - MAX_READ)
            pending = cursor.pending if same else b''
            if info.st_size - offset > MAX_READ:
                offset, pending = info.st_size - MAX_READ, b''
            dropped_prefix = offset > 0 and (not same or offset != cursor.offset)
            stream.seek(offset)
            raw = pending + stream.read(MAX_READ)
            next_offset = stream.tell()
        if dropped_prefix:
            raw = raw.partition(b'\n')[2]
            result['truncated'] = True
        lines = raw.split(b'\n')
        pending = lines.pop()
        if len(pending) > MAX_RECORD:
            # Retain one invalid marker so a continuation cannot become a record.
            pending = b'!' * (MAX_RECORD + 1)
        events = []
        for line in lines:
            try:
                value = _safe_record(json.loads(line)) if len(line) <= MAX_RECORD else None
            except (ValueError, UnicodeError, TypeError):
                value = None
            if value is None:
                result['discarded_records'] += 1
            else:
                events.append(value)
        result['events'] = events[-tail:]
        result['truncated'] |= len(events) > tail
        if result['discarded_records']:
            result['reason'] = 'LOG_RECORDS_WITHHELD'
        return result, LogCursor(identity, next_offset, pending)
    except FileNotFoundError:
        return {**result, 'state': 'missing', 'reason': 'LOG_NOT_FOUND'}, None
    except (OSError, ValueError):
        return {**result, 'state': 'unavailable', 'reason': 'LOG_UNAVAILABLE'}, None
