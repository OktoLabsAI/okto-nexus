"""Connection reuse, session choice and uncertain-send recovery are distinct."""
from dataclasses import dataclass

from ....application.terminal_connection import ConnectionError
from .native_input import display_text


@dataclass(frozen=True)
class SessionSelection:
    session_id: str | None = None
    new_session: bool = False


def pending_slots(flow):
    pending = []
    for name in ('work', 'control'):
        value = flow.document.get(name)
        if value is None:
            continue
        if not isinstance(value, dict) or not isinstance(value.get('state'), str):
            raise ConnectionError('CHECKPOINT_INVALID', 'Inspect the retained submission checkpoint before new work.')
        if value['state'] not in {'admitted', 'blocked'}:
            pending.append(name)
    return tuple(pending)


def session_inventory(flow):
    page = flow.sessions()
    if page.get('has_more'):
        raise ConnectionError('SESSION_SELECTION_REQUIRED', 'The bounded session inventory is incomplete. Use an explicit authorized --session-id or --new-session.')
    rows, seen = [], set()
    for row in page['sessions']:
        session_id = row.get('scope', {}).get('session_id')
        if not isinstance(session_id, str) or not session_id or session_id in seen:
            raise ConnectionError('SESSION_LIST_UNCONFIRMED', 'The session inventory contains invalid or duplicate references.')
        seen.add(session_id)
        rows.append(row)
    return tuple(rows)


def compatible_sessions(flow):
    return tuple(row for row in session_inventory(flow) if row.get('control_available') is True)


def choose_session(flow, *, read=input, write=print):
    inventory = session_inventory(flow)
    rows = tuple(row for row in inventory if row.get('control_available') is True)
    if not inventory:
        write('No compatible live session. A new context will open only after your request.')
        return SessionSelection(new_session=True)
    if not rows:
        write('Retained sessions cannot continue. History remains available with work status --session-id ID; starting another context requires New.')
    write('Choose the exact conversation context:')
    for index, row in enumerate(rows, 1):
        scope = row['scope']
        write(f'{index}. Continue {display_text(scope["session_id"])} '
            f'({display_text(row.get("lifecycle_state", "unconfirmed"))}; executor {display_text(scope.get("executor_id"))})')
    write('n. New conversation\nq. Leave without sending')
    while True:
        try:
            answer = read('Session: ').strip().lower()
        except EOFError:
            return None
        if answer in {'q', ''}:
            return None
        if answer == 'n':
            return SessionSelection(new_session=True)
        if answer.isdecimal() and 1 <= int(answer) <= len(rows):
            return SessionSelection(rows[int(answer) - 1]['scope']['session_id'])
        write('Select a displayed session, n, or q.')


def recover_before_selection(flow, display, *, read=input, write=print):
    """Recovery is an explicit action; observation/terminal exit never admits."""
    while slots := pending_slots(flow):
        write('An earlier submission is not resolved. New work is blocked until it is recovered.')
        for name in slots:
            write(f'{name}: {display_text(flow.document[name].get("client_intent_id"))}')
        try:
            choice = read('r. Recover original request / o. Observe / q. Leave: ').strip().lower()
        except EOFError:
            return False
        if choice in {'q', ''}:
            return False
        if choice not in {'r', 'o'}:
            continue
        for name in slots:
            try:
                display(flow.resume(name) if choice == 'r' else flow.observe(slot_name=name))
            except ConnectionError as error:
                display(dict(state='unconfirmed' if error.possible_effect else 'refused',
                    code=error.code, message=error.message, possible_effect=error.possible_effect))
                break
    return True
