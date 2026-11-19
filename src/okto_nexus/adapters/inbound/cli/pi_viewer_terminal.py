"""Wire the Windows terminal to the reviewed Pi draft editor."""

import codecs
import re
import sys
from uuid import uuid4

from ....application.terminal_connection import ConnectionError


_CSI = re.compile(r'\x1b\[[0-?]{0,48}[ -/]{0,4}[@-~]')
_START_PASTE, _END_PASTE = '\x1b[200~', '\x1b[201~'
_VT_KEYS = {
    '\x1b[A': 'up', '\x1b[B': 'down', '\x1b[C': 'right', '\x1b[D': 'left',
    '\x1b[H': 'home', '\x1b[F': 'end', '\x1b[3~': 'delete', '\x1b[13;2u': 'newline',
}
_WIN_KEYS = {35: 'end', 36: 'home', 37: 'left', 38: 'up', 39: 'right', 40: 'down', 46: 'delete'}
_CONTROLS = {'\x03': 'detach', '\x1d': 'detach', '\r': 'enter', '\x08': 'backspace', '\x7f': 'backspace'}
_MAX_DRAFT = 12 * 1024
_MAX_INSERT = 4 * 1024


def _printable(char):
    return char in '\t\n' or (' ' <= char and not '\x7f' <= char <= '\x9f')


def _bare_key(value):
    if value in _CONTROLS:
        return _CONTROLS[value], None
    return ('insert', value) if _printable(value) else (None, None)


def _key_from_csi(sequence):
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
    if modifiers & 0x0c and not modifiers & 0x13 and key in (0x43, 0xdd):
        return 'detach', None
    if 0 < code <= 0x10ffff and not 0xd800 <= code <= 0xdfff:
        return _bare_key(chr(code))
    return None, None


class _PiKeys:
    """Recognize bounded VT input, including split bracketed paste markers."""

    def __init__(self):
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
                key, text = _bare_key(char)
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
                key, text = _key_from_csi(value)
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


def show_pi_editor(link, recover):
    """Display Pi's editor and report durable receipt identities after Enter."""
    from .windows_viewer_terminal import ansi_viewer_output, viewer_console_input

    decode = codecs.getincrementaldecoder('utf-8')().decode

    def render(chunk):
        sys.stdout.write(decode(chunk))
        sys.stdout.flush()

    def status(text):
        print('\r\n' + text, flush=True)

    keys = _PiKeys()
    with ansi_viewer_output(sys.stdout), viewer_console_input(sys.stdin) as next_input:
        sys.stdout.write('\x1b[?2004h')
        sys.stdout.flush()
        try:
            while True:
                if output := link.poll_pi_output(.05):
                    render(output)
                incoming = next_input()
                if incoming is None:
                    return
                for key, text in keys.feed(incoming):
                    if key == 'detach':
                        return
                    intent = 'pi_input_' + uuid4().hex
                    try:
                        limited, queued = ((True, None) if key == 'limit' else
                            link.edit_pi_input(intent=intent, key=key, text=text, output=render))
                    except ConnectionError as error:
                        if not error.possible_effect:
                            raise
                        queued = recover(intent)
                        if queued is None:
                            status('Message delivery is unconfirmed. Use session receipt with intent ' + intent + '.')
                        else:
                            status('Message recorded as ' + queued['input_id'] + '.')
                        return
                    if limited:
                        status('The text exceeds the Pi editor limit.')
                    if queued is not None:
                        status('Message recorded as ' + queued['input_id'] + '.')
        finally:
            sys.stdout.write('\x1b[?2004l\x1b[0m\x1b[?25h\r\n')
            sys.stdout.flush()
