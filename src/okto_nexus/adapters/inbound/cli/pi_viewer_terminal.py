"""Wire the local terminal to the reviewed Pi draft editor."""

import codecs
import sys
import time
from dataclasses import dataclass
from uuid import uuid4

from ....application.terminal_connection import ConnectionError
from .terminal_editor import TerminalKeys, editor_terminal


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


def show_pi_editor(link, recover, *, allow_empty_open=False):
    """Display Pi's editor, keeping separate-session requests local to the CLI."""
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

    keys = TerminalKeys()
    controls = _PiControls(link, recover, render, status)
    draft_may_contain_text = False
    opening_review = False
    with editor_terminal() as next_input:
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
                    if opening_review:
                        if key == 'control_confirm':
                            return 'open_empty_session'
                        if key == 'control_cancel':
                            opening_review = False
                            status('Opening cancelled.')
                        break
                    if key == 'open_empty_session':
                        if not allow_empty_open:
                            continue
                        if draft_may_contain_text or controls.holds_draft or controls.receipts:
                            status('Finish the draft or pending control before opening a separate session.')
                            break
                        opening_review = True
                        status('Open a separate empty session in Nexus? Ctrl+Y confirms, Ctrl+N cancels. '
                               'The original session keeps its queue.')
                        break
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
                    elif key in ('insert', 'newline'):
                        draft_may_contain_text = True
                    elif key == 'enter':
                        draft_may_contain_text = False
                    if queued is not None:
                        status('Message recorded as ' + queued['input_id'] + '.')
        finally:
            sys.stdout.write('\x1b[?2004l\x1b[0m\x1b[?25h\r\n')
            sys.stdout.flush()
