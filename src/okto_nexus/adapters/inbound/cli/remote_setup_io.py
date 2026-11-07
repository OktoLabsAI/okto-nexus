"""Explicit remote setup review, public handoff and one-shot terminal delivery."""
from pathlib import Path
import json
import sys

from ....application.remote_setup_contract import normalize_draft, parse_document
from ....application.terminal_connection import ConnectionError
from ....domain.keys import is_well_formed_api_key
from ...outbound.service_manager.context import atomic_json, read_json


def read_draft(path):
    with Path(path).open('rb') as stream:
        return normalize_draft(parse_document(stream.read(65537)))


def material_sink(as_json):
    if as_json or not all(stream.isatty() for stream in (sys.stdin, sys.stdout, sys.stderr)):
        return None

    def deliver(key):
        if not is_well_formed_api_key(key):
            raise ConnectionError('MATERIAL_UNCONFIRMED',
                'The Server did not return a valid canonical agent key.', possible_effect=True)
        if not all(stream.isatty() for stream in (sys.stdin, sys.stdout, sys.stderr)):
            raise ConnectionError('MATERIAL_DELIVERY_UNAVAILABLE',
                'The interactive terminal is unavailable. The key was not written to a file or checkpoint.',
                possible_effect=True)
        print('\nCanonical agent key — shown once. Paste it into the Connector masked prompt:', file=sys.stderr)
        print(key, file=sys.stderr, flush=True)
        print('Keep this key if you need to resume import; the Server cannot recover its plaintext.\n', file=sys.stderr)
    return deliver


def handoff_sink(path, setup_run_id, *, as_json):
    path = Path(path).expanduser().absolute()
    if path.is_symlink() or not path.parent.is_dir():
        raise ConnectionError('HANDOFF_DESTINATION_INVALID', 'Select a regular handoff file in an existing directory.')

    def check_previous():
        if path.exists():
            old = read_json(path)
            if (old.get('format') != 'okto.remote-setup-handoff'
                    or old.get('bootstrap', {}).get('setup_run_id') != setup_run_id):
                raise ConnectionError('HANDOFF_DESTINATION_CONFLICT',
                    'The selected output file is not a handoff for this setup. Choose a different file.')
            return old
        return None

    check_previous()  # Refuse unrelated output before the bootstrap can create an identity.
    announced = False

    def export(value):
        nonlocal announced
        if (value.get('format') != 'okto.remote-setup-handoff'
                or value.get('bootstrap', {}).get('setup_run_id') != setup_run_id):
            raise ConnectionError('HANDOFF_UNCONFIRMED', 'The public handoff has another setup scope.', possible_effect=True)
        if check_previous() != value:
            atomic_json(path, value)
        if not as_json and not announced:
            print('Host handoff (contains no key): ' + str(path))
            print('Transfer this file to the execution host and resume Connector connect with --setup-receipt.')
            announced = True
    return export, str(path)


def display_review(document):
    review = document['remote_review']
    draft, selected = review['draft'], review['selection']
    identity, workspace = selected['identity'], selected['workspace']
    bootstrap = document.get('bootstrap')
    print('Server: ' + draft['server_origin'] + ' | Installation: ' + selected['server_id'])
    print('Remote execution host: ' + draft['connector_id'])
    identity_action = 'reuse committed' if bootstrap else identity['mode']
    print(f"Identity: {identity_action} {identity['agent_id']} ({identity['display_name']})")
    print('Role: ' + selected['identity_snapshot']['role'])
    print('Project: ' + draft['project_label'])
    print('Workspace: ' + (bootstrap['workspace_id'] if bootstrap else
        workspace['workspace_id'] or 'create ' + workspace['display_name']))
    print('Harness: ' + draft['installation']['adapter_id'])
    print('Selected installation: ' + draft['installation']['candidate_ref'])
    print('Canonical inventory: ' + (draft['installation']['inventory_revision'] or 'pending the consented host check'))
    print('Remote machine policy: ' + selected['remote_machine_policy'])
    for machine in selected['previous_machines']:
        print('Revoke previous machine authority at Finish: executor ' + machine['executor_id']
            + ', binding ' + machine['binding_id'] + ', endpoint ' + machine['endpoint_id']
            + ' (binding revision ' + str(machine['binding_revision'])
            + ', endpoint revision ' + str(machine['endpoint_revision']) + ')')
    permissions = selected['identity_snapshot']['permissions']
    for group, flags in permissions.items():
        if group == 'limits':
            print('Coordination limits: ' + ', '.join(name.replace('_', ' ') + '=' + str(value)
                for name, value in flags.items()))
        else:
            enabled = [name.replace('_', ' ') for name, value in flags.items() if value is True]
            disabled = [name.replace('_', ' ') for name, value in flags.items() if value is False]
            print(group.replace('_', ' ').capitalize() + ': enabled ' + (', '.join(enabled) or 'none')
                + '; disabled ' + (', '.join(disabled) or 'none'))
    for name, value in draft['configuration'].items():
        if name not in ('version', 'adapter_id', 'authorization'):
            print(name.replace('_', ' ').capitalize() + ': ' + json.dumps(value, ensure_ascii=False))
    grant = draft['configuration']['authorization']
    print('Execution authorization: ' + ('no expiry' if grant['minutes'] is None else str(grant['minutes']) + ' minutes')
        + '; ' + ('unlimited actions' if grant['actions'] is None else str(grant['actions']) + ' actions'))
    print('The reviewed project configuration permits authorized managed sessions and Nexus coordination.')
    print('Existing harness sandbox, project instructions and canonical decision rules remain effective.')
    if bootstrap:
        print('Use the canonical agent key already held for this committed identity.')
    elif identity['mode'] == 'create':
        print('Create this project identity and display its canonical key once in this terminal; no global administration is granted.')
    else:
        print('Import the existing canonical agent key on the host; this setup does not rotate it.')
    if selected['native_decision_policy']['initialize']:
        print('Enable Server-wide human review for native decisions; each decision still requires its authorized recipient.')
    print('Host login startup: ' + ('requested in the host review' if draft['start_at_login'] else 'preserve the current mode'))
    print('The host validates its selected installation after confirmation. No project task is submitted by setup.')
    print('Review revision: ' + review['review_revision'])
