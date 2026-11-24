"""Bounded keyboard input for the attached terminal editors."""

import codecs
import errno
import os
import re
import sys
from contextlib import contextmanager

from ....application.terminal_connection import ConnectionError


_CSI = re.compile(r'\x1b\[[0-?]{0,48}[ -/]{0,4}[@-~]')
_START_PASTE, _END_PASTE = '\x1b[200~', '\x1b[201~'
_VT_KEYS = {
    '\x1b[A': 'up', '\x1b[B': 'down', '\x1b[C': 'right', '\x1b[D': 'left',
    '\x1b[H': 'home', '\x1b[F': 'end', '\x1b[3~': 'delete', '\x1b[13;2u': 'newline',
}
_WIN_KEYS = {35: 'end', 36: 'home', 37: 'left', 38: 'up', 39: 'right', 40: 'down', 46: 'delete'}
_CONTROLS = {'\x03': 'detach', '\x1d': 'detach', '\r': 'enter', '\x08': 'backspace', '\x7f': 'backspace',
             '\x12': 'steer_review', '\x18': 'interrupt_review', '\x19': 'control_confirm', '\x0e': 'control_cancel',
             '\x0f': 'open_empty_session'}
_MAX_DRAFT = 12 * 1024
_MAX_INSERT = 4 * 1024


def _printable(char):
    return char in '\t\n' or (' ' <= char and not '\x7f' <= char <= '\x9f')


def _bare_key(value, controls):
    if value in controls:
        return controls[value], None
    return ('insert', value) if _printable(value) else (None, None)


def _key_from_csi(sequence, controls):
    if sequence in _VT_KEYS:
        return _VT_KEYS[sequence], None
    if not sequence.endswith('_'):
        return None, None
    fields = sequence[2:-1].split(';')
    if len(fields) != 6 or any(value and (not value.isascii() or not value.isdecimal()) for value in fields):
        return None, None
    key, _, code, down, modifiers, _ = (int(value or 0) for value in fields)
    if down != 1:
        return None, None
    if key in _WIN_KEYS:
        return _WIN_KEYS[key], None
    if key == 13 and modifiers & 0x10:  # SHIFT_PRESSED
        return 'newline', None
    if modifiers & 0x0c and not modifiers & 0x13:
        control = '\x1d' if key == 0xdd else chr(key - 0x40) if 0x41 <= key <= 0x5a else None
        if control in controls:
            return controls[control], None
    if 0 < code <= 0x10ffff and not 0xd800 <= code <= 0xdfff:
        return _bare_key(chr(code), controls)
    return None, None


class TerminalKeys:
    """Recognize bounded VT input, including split bracketed paste markers."""

    def __init__(self, *, shortcuts=None):
        self.controls = _CONTROLS | (shortcuts or {})
        self.pending = ''
        self.paste: list[str] | None = None
        self.pasted_bytes = 0

    def feed(self, incoming):
        self.pending += incoming
        actions = []
        typed = []
        size = 0

        def flush():
            nonlocal size
            if typed:
                actions.append(('insert', ''.join(typed)))
                typed.clear()
            size = 0

        def insert(value):
            nonlocal size
            for char in value:
                length = len(char.encode('utf-8'))
                if size + length > _MAX_INSERT:
                    flush()
                typed.append(char)
                size += length

        while self.pending:
            if self.paste is not None:
                end = self.pending.find(_END_PASTE)
                take = end if end >= 0 else max(0, len(self.pending) - len(_END_PASTE) + 1)
                part, self.pending = self.pending[:take], self.pending[take:]
                self.pasted_bytes += len(part.encode('utf-8'))
                if self.pasted_bytes <= _MAX_DRAFT:
                    self.paste.append(part)
                if end < 0:
                    break
                self.pending = self.pending[len(_END_PASTE):]
                if self.pasted_bytes <= _MAX_DRAFT:
                    cleaned = ''.join(self.paste).replace('\r\n', '\n').replace('\r', '\n')
                    insert(''.join(char for char in cleaned if _printable(char)))
                else:
                    flush()
                    actions.append(('limit', None))
                self.paste = None
                continue

            char = self.pending[0]
            if char != '\x1b':
                self.pending = self.pending[1:]
                key, text = _bare_key(char, self.controls)
            elif self.pending.startswith('\x1b['):
                sequence = _CSI.match(self.pending)
                if sequence is None:
                    if len(self.pending) <= 55:
                        break
                    # Drop the invalid escape frame as a unit.
                    self.pending = ''
                    break
                value = sequence[0]
                self.pending = self.pending[sequence.end():]
                if value == _START_PASTE:
                    self.paste, self.pasted_bytes = [], 0
                    continue
                key, text = _key_from_csi(value, self.controls)
            elif len(self.pending) == 1:
                break
            else:
                self.pending = self.pending[2:]
                continue

            if key == 'insert':
                insert(text)
            elif key is not None:
                flush()
                actions.append((key, None))
        flush()
        return actions


@contextmanager
def _posix_editor_input(stream):
    import select
    import termios
    import tty

    fd = stream.fileno()
    try:
        original = termios.tcgetattr(fd)
        tty.setraw(fd, termios.TCSAFLUSH)
    except termios.error:
        raise ConnectionError('PRESENTATION_TTY_REQUIRED', 'The viewer editor needs an interactive terminal.') from None
    decode = codecs.getincrementaldecoder('utf-8')(errors='replace').decode

    def take():
        if not select.select([fd], [], [], 0)[0]:
            return ''
        try:
            raw = os.read(fd, _MAX_INSERT)
        except OSError as error:
            if error.errno == errno.EIO:  # The terminal can disappear on hangup.
                return None
            raise
        return decode(raw) if raw else None

    try:
        yield take
    finally:
        try:
            termios.tcsetattr(fd, termios.TCSAFLUSH, original)
        except termios.error as error:
            if error.args[0] not in (errno.EIO, errno.ENOTTY):
                raise


@contextmanager
def editor_terminal():
    if sys.platform == 'win32':
        from .windows_viewer_terminal import ansi_viewer_output, viewer_console_input

        with ansi_viewer_output(sys.stdout), viewer_console_input(sys.stdin) as read:
            yield read
    else:
        with _posix_editor_input(sys.stdin) as read:
            yield read
