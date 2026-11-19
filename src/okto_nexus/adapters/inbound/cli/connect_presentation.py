"""Keep configured connection receipts independent of terminal presentation."""

import os

from ....application.terminal_connection import ConnectionError
from ....errors import OktoNexusError
from .native_input import display_text

_SCOPE_KEYS = ('server_id', 'executor_id', 'binding_id', 'agent_id', 'workspace_id', 'workspace_binding_id')


def interaction_preview(value, args, *, profile, home, terminal, service_args, operator_profile=None):
    """Project the requested surface without admitting or selecting a session."""
    if args.interactive:
        requested = 'native_terminal'
    elif args.no_interactive or args.no_chat or not terminal:
        requested = 'none'
    else:
        requested = 'ask'
    configured = value['state'] == 'configured' and not args.plan
    status = 'planned' if args.plan else 'pending_setup'
    if configured:
        status = {'native_terminal': 'requested', 'none': 'not_requested', 'ask': 'offer'}[requested]
    interaction = {'requested_surface': requested, 'resolved_surface': 'none',
                   'status': status, 'setup_success': configured}
    if configured:
        public = value.get('public_connection') or {}
        confirmed = public.get('state') == 'bound' and bool(public.get('canonical_ref'))
        reference = public['canonical_ref'] if confirmed else value
        scope = {name: reference[name] for name in _SCOPE_KEYS if reference.get(name) is not None}
        if scope:
            interaction['scope'] = scope
        argv = ['okto-nexus', 'session', 'attach']
        if confirmed:
            workspace_id = reference['workspace_id']
            argv.extend(('--id', public['connect_id'], '--workspace-id=' + workspace_id))
        else:
            argv.extend(('--profile', profile))
        # Carry the service options that affect how the terminal finds the
        # selected instance. Discovery and setup options are irrelevant here.
        _target_options(argv, home, service_args)
        if operator_profile:
            argv.extend(('--operator-profile', operator_profile))
        interaction['attach_argv'] = argv
        interaction['capability_state'] = 'unconfirmed'
    return interaction


def _target_options(argv, home, service_args):
    argv.extend(('--home', str(home)))
    tokens = iter(service_args)
    for token in tokens:
        flag, equals, _ = token.partition('=')
        if flag in ('--host', '--port'):
            argv.append(token)
            if not equals:
                argv.append(next(tokens))


def display_attach_command(interaction):
    if interaction['status'] == 'planned' and interaction['requested_surface'] == 'native_terminal':
        print('Plan requests the native viewer after setup.')
    argv = interaction.get('attach_argv')
    if argv:
        _display_command('Inspect a session later: ', argv)


def _display_command(label, argv):
    from .quick_connect_render import render_resume_command
    try:
        command = render_resume_command(argv, shell='powershell' if os.name == 'nt' else 'posix')
    except ValueError:
        return
    print(label + command)


def display_reattach_command(attached, binding, *, service, operator_profile=None, write=False, viewer_executable=None):
    """After detach, render only the confirmed binding and session for the human login."""
    if not attached or attached['status'] != 'detached':
        return
    login = getattr(service, 'operator_profile', operator_profile)
    revision = binding.get('binding_revision')
    if not login or type(revision) is not int or not 0 < revision < 2**63:
        return
    scope = attached['scope']
    fields = ('binding_id', 'server_id', 'executor_id', 'workspace_id')
    if any(scope.get(key) != binding.get(key) for key in fields):
        return
    selectors = {key.replace('_', '-'): scope.get(key) for key in (*fields, 'session_id')}
    selectors.update({'binding-revision': str(revision), 'operator-profile': login,
                      'home': str(service.adapter.home)})
    if viewer_executable is not None:
        selectors['viewer-executable'] = str(viewer_executable.absolute())
    if any(not isinstance(value, str) or not value or not value.isprintable() for value in selectors.values()):
        return
    argv = ['okto-nexus', 'session', 'attach', *(f'--{key}={value}' for key, value in selectors.items())]
    if write:
        argv.append('--write')
    _display_command('Reattach to this session: ', argv)


def present_after_connect(service, *, profile, document, interaction):
    """The configured receipt is already durable before this separate action."""
    if interaction['status'] not in ('offer', 'requested'):
        return
    try:
        if interaction['status'] == 'offer':
            harness = display_text(document['selection']['client'])
            if input(f'Open {harness} in this terminal? [y/N] ').strip().lower() != 'y':
                return
        from .session import attach_session
        from .work import open_work
        flow = open_work(service, profile, connection=document)
        binding = flow.binding()
        attached = attach_session(flow.call, binding, interactive=True)
        display_reattach_command(attached, binding, service=service)
    except EOFError:
        return
    except KeyboardInterrupt:
        print('Native viewer canceled. Connection configured.')
    except ConnectionError as error:
        print('Native viewer unavailable. Connection configured. ' + display_text(error.message))
    except (OSError, OktoNexusError, TypeError, ValueError, KeyError):
        print('Native viewer unavailable. Connection configured. Inspect the saved connection before attaching.')
