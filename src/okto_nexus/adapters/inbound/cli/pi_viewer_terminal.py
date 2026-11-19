"""Wire the Windows terminal to the reviewed Pi draft editor."""

import codecs
import re
import sys
import time
from uuid import uuid4

from ....application.terminal_connection import ConnectionError


_CSI = re.compile(r'\x1b\[[0-?]{0,48}[ -/]{0,4}[@-~]')
_START_PASTE, _END_PASTE = '\x1b[200~', '\x1b[201~'
_VT_KEYS = {
    '\x1b[A': 'up', '\x1b[B': 'down', '\x1b[C': 'right', '\x1b[D': 'left',
    '\x1b[H': 'home', '\x1b[F': 'end', '\x1b[3~': 'delete', '\x1b[13;2u': 'newline',
}
_WIN_KEYS = {35: 'end', 36: 'home', 37: 'left', 38: 'up', 39: 'right', 40: 'down', 46: 'delete'}
_CONTROLS = {'\x03': 'detach', '\x1d': 'detach', '\r': 'enter', '\x08': 'backspace', '\x7f': 'backspace',
             '\x12': 'steer_review', '\x19': 'steer_confirm', '\x0e': 'steer_cancel'}
_STEER_KEYS = {'steer_review', 'steer_confirm', 'steer_cancel'}
_STEER_STATUS = {
    'pending': 'Reorientation recorded. Waiting for delivery.',
    'submitted': 'Reorientation sent. Application is unconfirmed.',
    'awaiting_boundary': 'Pi queued the reorientation for the next boundary.',
    'applied': 'Pi applied the reorientation.',
    'discarded': 'The run ended before Pi applied the reorientation. Your draft is available.',
    'refused': 'The reorientation was refused before sending. Your draft is available.',
    'unconfirmed': 'Application is unconfirmed. Use the receipt to check this request.',
}
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
    if modifiers & 0x0c and not modifiers & 0x13 and key in (0x52, 0x59, 0x4e):
        return {0x52: 'steer_review', 0x59: 'steer_confirm', 0x4e: 'steer_cancel'}[key], None
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


class _PiSteer:
    """Keep one review or recorded draft until the exact receipt settles."""

    def __init__(self, link, recover, render, status):
        self.link, self.recover, self.render, self.status = link, recover, render, status
        self.review_id = self.intent = self.input_id = self.previous = None
        self.next_poll = 0.0

    @property
    def holds_draft(self):
        return self.review_id is not None or self.input_id is not None

    def recover_notice(self):
        receipt = self.recover(self.intent)
        boundary = receipt.get('steer_boundary') if receipt else None
        if boundary in ('applied', 'discarded'):
            self.status(_STEER_STATUS[boundary])
        else:
            self.status('Reorientation is unconfirmed. Use session receipt with intent ' + self.intent + '.')

    def key(self, key):
        """Return true when an uncertain productive response requires detaching."""
        if self.input_id is not None:
            return False
        if self.review_id is None:
            if key == 'steer_review':
                self.intent = 'pi_steer_' + uuid4().hex
                self.review_id = self.link.review_pi_steer(intent=self.intent, output=self.render)
                self.status('Reorient this Pi run at its next available boundary? Ctrl+Y confirms. Ctrl+N cancels.'
                            if self.review_id else 'Reorientation is unavailable for this draft or execution.')
            return False
        if key not in ('steer_cancel', 'steer_confirm'):
            return False
        confirm = key == 'steer_confirm'
        try:
            self.input_id = self.link.decide_pi_steer(review_id=self.review_id, confirm=confirm, output=self.render)
        except ConnectionError as error:
            if not error.possible_effect:
                raise
            self.recover_notice()
            return True
        self.review_id = None
        if self.input_id:
            self.previous = 'pending'
            self.next_poll = time.monotonic()
            self.status(_STEER_STATUS['pending'])
        elif confirm:
            self.status('The reorientation review changed. Your draft is available.')
        else:
            self.status('Reorientation cancelled. Your draft is available.')
        return False

    def poll(self):
        if self.input_id is None or time.monotonic() < self.next_poll:
            return
        self.next_poll = time.monotonic() + 1
        state = self.link.pi_steer_status(input_id=self.input_id, output=self.render)
        if state != self.previous:
            self.previous = state
            self.status(_STEER_STATUS[state])
        if state in ('applied', 'discarded', 'refused'):
            self.input_id = None


def show_pi_editor(link, recover):
    """Display Pi's editor and report durable receipt identities after Enter."""
    from .windows_viewer_terminal import ansi_viewer_output, viewer_console_input

    decode = codecs.getincrementaldecoder('utf-8')().decode
    notice = ''

    def render(chunk):
        text = decode(chunk)
        sys.stdout.write(text)
        if notice and '\x1b[2J' in text:
            sys.stdout.write('\r\n' + notice)
        sys.stdout.flush()

    def status(text):
        nonlocal notice
        notice = text
        print('\r\n' + text, flush=True)

    keys = _PiKeys()
    steer = _PiSteer(link, recover, render, status)
    with ansi_viewer_output(sys.stdout), viewer_console_input(sys.stdin) as next_input:
        sys.stdout.write('\x1b[?2004h')
        sys.stdout.flush()
        try:
            while True:
                try:
                    if output := link.poll_pi_output(.05):
                        render(output)
                    steer.poll()
                except ConnectionError:
                    if steer.input_id is None:
                        raise
                    steer.recover_notice()
                    return
                incoming = next_input()
                if incoming is None:
                    return
                for key, text in keys.feed(incoming):
                    if key == 'detach':
                        if steer.input_id is not None:
                            status('Reorientation receipt intent ' + steer.intent + '.')
                        return
                    if key in _STEER_KEYS:
                        if steer.key(key):
                            return
                        # Confirmation must arrive in a later terminal read.
                        break
                    if steer.holds_draft:
                        continue
                    notice = ''
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
