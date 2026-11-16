"""Human connection intent, separate from setup and session selection."""
from dataclasses import asdict


def selection_required(catalog, *, reason='connection_selection_required', lifecycle_requested=False):
    return dict(state='selection_required', reason=reason,
        # connect may already have ensured the service; never claim no effects.
        effects_started=None if lifecycle_requested else False,
        lifecycle_requested=lifecycle_requested,
        choices=[asdict(row) for row in catalog.choices],
        catalog_complete=catalog.complete,
        issues=[asdict(issue) for issue in catalog.issues])


def pick_connection(catalog, *, client=None, read=input, write=print):
    """Return ('resume', profile), ('add', None), or ('cancel', None).

    A client filter offers another connection, never silently changes an old
    profile. Pending choices remain visible even when their harness differs.
    """
    if not catalog.complete:
        return 'unconfirmed', None
    candidates = [row for row in catalog.choices if client in (None, row.client)
        or row.setup_pending or row.work_pending or row.control_pending
        or row.authorization_pending or row.decision_pending or row.startup_pending]
    if not catalog.choices:
        return 'add', None
    write('Choose a project connection (selection does not submit work):')
    for index, row in enumerate(candidates, 1):
        pending = any((row.setup_pending, row.work_pending, row.control_pending,
            row.authorization_pending, row.decision_pending, row.startup_pending))
        write(f'{index}. Resume {row.client or "harness unconfirmed"} / {row.agent_id} / {row.profile}'
              + f' [Server host; {row.setup_state}]'
              + (' (recover pending checkpoint first)' if pending else ''))
    write('a. Add another connection\nc. Cancel')
    while True:
        try:
            answer = read('Connection: ').strip().lower()
        except EOFError:
            return 'cancel', None
        if answer == 'a':
            return 'add', None
        if answer in {'c', ''}:
            return 'cancel', None
        if answer.isdecimal() and 1 <= int(answer) <= len(candidates):
            return 'resume', candidates[int(answer) - 1].profile
        write('Select a displayed connection, a, or c.')


def pick_harness(choices, *, read=input, write=print):
    """Only choices returned by the canonical inventory; no label inference."""
    choices = tuple(choices)
    write('Choose an observed harness:')
    for index, client in enumerate(choices, 1):
        write(f'{index}. {client}')
    write('c. Cancel')
    while True:
        try:
            answer = read('Harness: ').strip().lower()
        except EOFError:
            return None
        if answer in {'', 'c'}:
            return None
        if answer.isdecimal() and 1 <= int(answer) <= len(choices):
            return choices[int(answer) - 1]
        write('Select a displayed harness or c.')
