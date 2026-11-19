"""Wire the Windows terminal to the reviewed Pi draft editor."""

import codecs
import re
import sys
import time
from dataclasses import dataclass
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
             '\x12': 'steer_review', '\x18': 'interrupt_review', '\x19': 'control_confirm', '\x0e': 'control_cancel'}
_CONTROL_KEYS = {'steer_review', 'interrupt_review', 'control_confirm', 'control_cancel'}
_CONTROL_NAMES = {'steer': 'Reorientation', 'interrupt': 'Interruption'}
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
    if modifiers & 0x0c and not modifiers & 0x13 and key in (0x52, 0x58, 0x59, 0x4e):
        return {0x52: 'steer_review', 0x58: 'interrupt_review', 0x59: 'control_confirm', 0x4e: 'control_cancel'}[key], None
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


def _interrupt_notice(result):
    state = result['target_status']
    if state == 'interrupted':
        message = 'The selected Pi execution was interrupted.'
    elif state == 'finished':
        message = 'The selected Pi execution already ended.'
    elif result['refused']:
        message = 'Interruption was refused before it took effect.'
    elif result['outcome_unknown']:
        message = 'Interruption is unconfirmed.'
    else:
        message = 'Interruption recorded. Waiting for the selected Pi execution to stop.'
    if result['queue_paused']:
        message += ' The message queue is paused.'
    return message


@dataclass(frozen=True, slots=True)
class _ControlReview:
    action: str
    intent: str
    review_id: str


@dataclass(slots=True)
class _ControlReceipt:
    intent: str
    input_id: str | None
    previous_message: str | None = None


class _PiControls:
    """Track an explicit review and the exact receipts of recorded controls."""

    def __init__(self, link, recover, render, status):
        self.link, self.recover, self.render, self.status = link, recover, render, status
        self.review: _ControlReview | None = None
        self.receipts: dict[str, _ControlReceipt] = {}
        self.next_poll = 0.0

    @property
    def holds_draft(self):
        return self.review is not None or 'steer' in self.receipts

    def recover_notice(self, action, intent):
        receipt = self.recover(intent)
        if action == 'steer' and receipt and receipt.get('steer_boundary') in ('applied', 'discarded'):
            self.status(_STEER_STATUS[receipt['steer_boundary']])
        elif action == 'interrupt' and receipt and receipt['interrupt']['target_status'] in ('interrupted', 'finished'):
            self.status(_interrupt_notice(receipt['interrupt'] | {'refused': False, 'outcome_unknown': False}))
        else:
            self.status(f'{_CONTROL_NAMES[action]} is unconfirmed. Use session receipt with intent {intent}.')

    def key(self, key):
        """Return true when an uncertain productive response requires detaching."""
        if self.review is None:
            if key in ('steer_review', 'interrupt_review'):
                action = key.split('_')[0]
                if action in self.receipts:
                    return False
                intent = f'pi_{action}_' + uuid4().hex
                review_id = self.link.review_pi_control(action=action, intent=intent, output=self.render)
                if review_id is None:
                    self.status(f'{_CONTROL_NAMES[action]} is unavailable for the selected execution.')
                else:
                    self.review = _ControlReview(action, intent, review_id)
                    question = ('Reorient this Pi run at its next available boundary?' if action == 'steer'
                                else 'Interrupt this Pi execution and pause the message queue?')
                    self.status(question + ' Ctrl+Y confirms. Ctrl+N cancels.')
            return False
        if key not in ('control_cancel', 'control_confirm'):
            return False
        review, self.review = self.review, None
        confirm = key == 'control_confirm'
        try:
            reply = self.link.decide_pi_control(action=review.action, review_id=review.review_id,
                                                confirm=confirm, output=self.render)
        except ConnectionError as error:
            if not error.possible_effect:
                raise
            self.recover_notice(review.action, review.intent)
            return True
        if reply:
            self.receipts[review.action] = _ControlReceipt(review.intent, reply.get('input_id'))
            self.next_poll = time.monotonic()
            self.status(_STEER_STATUS['pending'] if review.action == 'steer'
                        else 'Interruption recorded. Checking the selected execution and queue.')
        elif confirm:
            self.status(f'The {_CONTROL_NAMES[review.action].lower()} review changed. Your draft is available.')
        else:
            self.status(f'{_CONTROL_NAMES[review.action]} cancelled. Your draft is available.')
        return False

    def poll(self):
        if not self.receipts or self.review is not None or time.monotonic() < self.next_poll:
            return
        self.next_poll = time.monotonic() + 1
        for action, receipt in tuple(self.receipts.items()):
            if action == 'steer':
                state = self.link.pi_steer_status(input_id=receipt.input_id, output=self.render)
                message = _STEER_STATUS[state]
                settled = state in ('applied', 'discarded', 'refused')
            else:
                result = self.link.pi_interrupt_status(intent=receipt.intent, output=self.render)
                message = _interrupt_notice(result)
                settled = result['target_status'] in ('interrupted', 'finished') or result['refused']
            if message != receipt.previous_message:
                receipt.previous_message = message
                self.status(message)
            if settled:
                del self.receipts[action]


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
    controls = _PiControls(link, recover, render, status)
    with ansi_viewer_output(sys.stdout), viewer_console_input(sys.stdin) as next_input:
        sys.stdout.write('\x1b[?2004h')
        sys.stdout.flush()
        try:
            while True:
                try:
                    if output := link.poll_pi_output(.05):
                        render(output)
                    controls.poll()
                except ConnectionError:
                    if not controls.receipts:
                        raise
                    for action, receipt in controls.receipts.items():
                        controls.recover_notice(action, receipt.intent)
                    return
                incoming = next_input()
                if incoming is None:
                    return
                for key, text in keys.feed(incoming):
                    if key == 'detach':
                        for action, receipt in controls.receipts.items():
                            status(f'{_CONTROL_NAMES[action]} receipt intent {receipt.intent}.')
                        return
                    if key in _CONTROL_KEYS:
                        if controls.key(key):
                            return
                        # Confirmation must arrive in a later terminal read.
                        break
                    if controls.holds_draft:
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
