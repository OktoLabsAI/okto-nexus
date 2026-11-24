"""Follow the managed Claude terminal and submit a structured Nexus draft."""

import codecs
import sys
from dataclasses import dataclass
from uuid import uuid4

from ....application.terminal_connection import ConnectionError
from .terminal_editor import TerminalKeys, editor_terminal


_DRAFT_BYTES = 12 * 1024
_BUFFER_CHARACTERS = 32 * 1024
_CONTROL_NAMES = {'steer': 'Reorientation', 'interrupt': 'Interruption'}


@dataclass(frozen=True, slots=True)
class _Review:
    action: str
    intent: str
    review_id: str
    return_to_draft: bool


class _Draft:
    def __init__(self):
        self.text = ''
        self.cursor = 0

    def valid(self):
        return bool(self.text.strip() and not self.text.lstrip().startswith(('/', '!')) and '\t' not in self.text)

    def edit(self, key, text):
        position = self.cursor
        left, right = self.text[:position], self.text[position:]
        if key in ('insert', 'newline'):
            value = '\n' if key == 'newline' else text
            edited = left + value + right
            if len(edited.encode('utf-8')) > _DRAFT_BYTES:
                return False
            self.text, self.cursor = edited, position + len(value)
        elif key == 'backspace' and left:
            self.text, self.cursor = left[:-1] + right, position - 1
        elif key == 'delete':
            self.text = left + right[1:]
        elif key == 'left':
            self.cursor = max(0, position - 1)
        elif key == 'right':
            self.cursor = min(len(self.text), position + 1)
        elif key in ('home', 'end'):
            self.cursor = 0 if key == 'home' else len(self.text)
        return key != 'limit'


def show_claude_writer(link, recover, report_intent):
    """Edit a local draft while reading the exact owner's retained output."""
    decoder = codecs.getincrementaldecoder('utf-8')()
    keys = TerminalKeys(shortcuts={'\x05': 'compose'})
    draft = _Draft()
    composing = False
    review = None
    buffered = []
    buffered_size = 0

    def write(text):
        sys.stdout.write(text)
        sys.stdout.flush()

    def render_draft(notice=''):
        left, right = draft.text[:draft.cursor], draft.text[draft.cursor:]
        # The cursor marker is local. Only the original draft is submitted.
        visible = left + '\x1b[7m' + (right[:1] or ' ') + '\x1b[27m' + right[1:]
        write('\x1b[H\x1b[2JMessage to Claude\r\n'
              'Enter queues · Ctrl+R reviews reorientation · Ctrl+N discards · Ctrl+E returns to output\r\n\r\n'
              + visible.replace('\n', '\r\n') + ('\r\n\r\n' + notice if notice else ''))

    def leave_composer():
        nonlocal composing, buffered_size
        composing = False
        write('\x1b[?1049l' + ''.join(buffered))
        buffered.clear()
        buffered_size = 0

    def render_output(chunk):
        nonlocal buffered_size, review
        text = decoder.decode(chunk)
        if not composing:
            write(text)
            return
        buffered.append(text)
        buffered_size += len(text)
        if buffered_size >= _BUFFER_CHARACTERS:
            leave_composer()
            review = None
            write('\r\nDraft kept. Press Ctrl+E to continue editing.\r\n')

    def begin_review(action):
        nonlocal composing
        intent = f'claude_{action}_' + uuid4().hex
        original_mode = composing
        target = link.review_claude_control(action=action, intent=intent, output=render_output,
                                           text=draft.text if action == 'steer' else None)
        if target is None:
            notice = _CONTROL_NAMES[action] + ' is unavailable for the active Claude turn.'
            if composing:
                render_draft(notice)
            else:
                write('\r\n' + notice + '\r\n')
            return None
        review_id, operation = target
        if not composing:
            composing = True
            write('\x1b[?1049h')
        effect = ('Interrupt this turn and send the replacement below?' if action == 'steer'
                  else 'Interrupt this turn and pause the message queue?')
        prompt = f'\x1b[H\x1b[2JClaude turn {operation[-8:]}\r\n{effect}\r\nCtrl+Y confirms · Ctrl+N cancels\r\n'
        write(prompt + ('\r\n' + draft.text.replace('\n', '\r\n') if action == 'steer' else ''))
        return _Review(action, intent, review_id, original_mode)

    def commit(intent, submit, *, label='Message'):
        report_intent(intent)
        try:
            return submit(), False
        except ConnectionError as error:
            if not error.possible_effect:
                raise
            recovered = recover(intent)
            write('\r\n' + (recovered['message'] if recovered else
                  label + ' delivery is unconfirmed. Check the receipt before trying again.') + '\r\n')
            return None, True

    try:
        with editor_terminal() as next_input:
            write('\x1b[?2004h')
            try:
                while True:
                    if output := link.poll_terminal_output(.05):
                        render_output(output)
                    incoming = next_input()
                    if incoming is None:
                        return
                    actions = keys.feed(incoming)
                    if any(key == 'detach' for key, _ in actions):
                        return
                    may_submit = composing
                    for key, text in actions:
                        if review is not None:
                            if key not in ('control_confirm', 'control_cancel'):
                                continue
                            selected, review = review, None
                            if key == 'control_cancel':
                                link.decide_terminal_control(action=selected.action, review_id=selected.review_id,
                                                             confirm=False, output=render_output)
                                if selected.return_to_draft and composing:
                                    render_draft(_CONTROL_NAMES[selected.action] + ' cancelled.')
                                elif composing:
                                    leave_composer()
                                break
                            leave_composer()
                            decision, uncertain = commit(selected.intent, lambda: link.decide_terminal_control(
                                action=selected.action, review_id=selected.review_id, confirm=True, output=render_output),
                                label=_CONTROL_NAMES[selected.action])
                            if uncertain:
                                return
                            if decision is None:
                                write('\r\nThe review changed. Press Ctrl+E to open your draft.\r\n')
                            else:
                                if selected.action == 'steer':
                                    draft = _Draft()
                                write('\r\n' + _CONTROL_NAMES[selected.action] + ' recorded. Check the receipt for the outcome.\r\n')
                            break
                        if key == 'interrupt_review':
                            review = begin_review('interrupt')
                            break
                        if key == 'compose':
                            may_submit = False
                            if composing:
                                leave_composer()
                            else:
                                composing = True
                                write('\x1b[?1049h')
                                render_draft()
                            # An Enter in the same read as the toggle cannot submit.
                            continue
                        if not composing:
                            continue
                        if key == 'control_cancel':
                            draft = _Draft()
                            leave_composer()
                            break
                        if key == 'steer_review':
                            if may_submit and draft.valid():
                                review = begin_review('steer')
                            else:
                                render_draft('Enter the replacement message before reviewing reorientation.')
                            break
                        if key != 'enter':
                            if not draft.edit(key, text):
                                render_draft('This message is too long.')
                                break
                            render_draft()
                            continue
                        if not may_submit:
                            break
                        if not draft.valid():
                            render_draft('Enter plain text without a terminal command or tab.')
                            break
                        intent = 'claude_input_' + uuid4().hex
                        leave_composer()
                        receipt, uncertain = commit(intent, lambda: link.send_terminal_input(
                            intent=intent, text=draft.text, output=render_output))
                        if uncertain:
                            return
                        draft = _Draft()
                        write('\r\nMessage recorded as ' + receipt['input_id'] + '.\r\n')
                        break
            finally:
                if composing:
                    leave_composer()
                write('\x1b[?2004l\x1b[0m\x1b[?25h\r\n')
    except UnicodeError:
        raise ConnectionError('PRESENTATION_UNAVAILABLE', 'The Claude terminal returned invalid text.') from None
    except OSError:
        raise ConnectionError('PRESENTATION_TTY_REQUIRED', 'The terminal could not display the Claude viewer.') from None
