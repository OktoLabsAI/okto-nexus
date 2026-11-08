"""Bounded SQLite failure metadata; never exception text, SQL or paths."""
import sqlite3

from .write_gate import WriterAdmissionTimeout


_PRIMARY_NAMES = {
    getattr(sqlite3, 'SQLITE_' + name): 'SQLITE_' + name
    for name in ('ERROR', 'INTERNAL', 'PERM', 'ABORT', 'BUSY', 'LOCKED', 'NOMEM',
                 'READONLY', 'INTERRUPT', 'IOERR', 'CORRUPT', 'NOTFOUND', 'FULL',
                 'CANTOPEN', 'PROTOCOL', 'EMPTY', 'SCHEMA', 'TOOBIG', 'CONSTRAINT',
                 'MISMATCH', 'MISUSE', 'NOLFS', 'AUTH', 'FORMAT', 'RANGE', 'NOTADB',
                 'NOTICE', 'WARNING')
}


def safe_db_diagnostic(error):
    """Project actual typed causes, without guessing from their messages.

    Retryability is the nearest explicit boolean policy, not permission to
    replay an operation. A gate timeout is distinct from a SQLite BUSY result.
    Suppressed contexts and oversized/cyclic chains do not invent a cause.
    """
    result = {}
    seen = set()
    current = error
    for _ in range(16):
        if not isinstance(current, BaseException) or id(current) in seen:
            break
        seen.add(id(current))
        retryable = getattr(current, 'retryable', None)
        if 'retryable' not in result and type(retryable) is bool:
            result['retryable'] = retryable
        if isinstance(current, WriterAdmissionTimeout):
            result['writer_gate_timeout'] = True
        if isinstance(current, sqlite3.Error) and 'sqlite_errorcode' not in result:
            code = getattr(current, 'sqlite_errorcode', None)
            if type(code) is int and 0 <= code <= 0x7fffffff and code & 255 in _PRIMARY_NAMES:
                primary = _PRIMARY_NAMES[code & 255]
                result.update(sqlite_errorcode=code, sqlite_primary_errorcode=code & 255,
                              sqlite_primary_errorname=primary)
                name = getattr(current, 'sqlite_errorname', None)
                if (type(name) is str and (name == primary or name.startswith(primary + '_'))
                        and len(name) <= 80 and getattr(sqlite3, name, None) == code):
                    result['sqlite_errorname'] = name
        cause = current.__cause__
        current = cause if cause is not None else (
            None if current.__suppress_context__ else current.__context__)
    return result
