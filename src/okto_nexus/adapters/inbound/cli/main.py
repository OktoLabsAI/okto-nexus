"""HTTP-only Nexus command entry point.

Harness native stdio protocols belong to the Core. Nexus MCP is served only
through ``okto-nexus serve`` and its HTTP ``/mcp`` endpoint.
"""

from __future__ import annotations

import sys

_HELP = """okto-nexus - local agent coordination bus

Usage:
  okto-nexus connect [harness] [project-name] [--id HARNESS_ID] [options]
  okto-nexus codex|claude|pi [project-name] [--id HARNESS_ID] [options]
  okto-nexus init --mode participant [options] Review an existing agent's external MCP configuration
  okto-nexus participant launch [--profile NAME] [--plan | --approve REVISION] [options]  Launch a client with its protected credential
  okto-nexus participant remove [--profile NAME] [--plan | --approve REVISION] [options]  Remove this setup's local entry and credential
  okto-nexus participant smoke exchange|handoff|status|observe [options]  Review optional cooperation with a peer
  okto-nexus doctor [--mode managed|participant] [--profile NAME] [--check-server] [--json]  Inspect independent proof levels
  okto-nexus preset [--plan | --approve REVISION] [options]  Review optional preset updates
  okto-nexus work [chat|send|status|watch|events|answer|authorize|sessions|resume|steer|interrupt|close] [options]
  okto-nexus session list|attach|resume [--id HARNESS_ID | --profile NAME] [options]
  okto-nexus message send [options]  Send conversation using a participant profile
  okto-nexus handoff create|wait [options]  Create work or observe its canonical completion
  okto-nexus request inspect [REQUEST_ID] [options]  Recover a coordination reference
  okto-nexus observe herdr bind|run|status [options]  Publish optional external activity observations
  okto-nexus operator login|status|logout --profile NAME [options]
  okto-nexus operator approval APPROVAL_ID --profile NAME [options]
  okto-nexus serve [options]   Start HTTP MCP, REST and dashboard
  okto-nexus service status|logs|start|stop|restart|recover-start|install|uninstall|enable|disable|upgrade-plan|upgrade-apply [options]  Manage the local Server
  okto-nexus tail [options]    Stream the event log as NDJSON
  okto-nexus admin <command>   Run maintenance commands
  okto-nexus provider-credentials <set|remove>  Manage provider secrets

Use `okto-nexus serve --help` for server options. Agents connect to /mcp
over HTTP with their existing API key.
"""


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:]) if argv is None else list(argv)
    if not args or args[0] in ("-h", "--help", "help"):
        print(_HELP)
        return 0
    command, rest = args[0], args[1:]
    if command == 'observe':
        from .observe import run_observe
        return run_observe(rest)
    if command in ('message', 'handoff', 'request'):
        from .coordination import run_coordination
        return run_coordination(command, rest)
    if command == 'connect':
        from .connect import run_connect
        return run_connect(rest)
    if command == 'init':
        from .participant import run_participant
        return run_participant(rest)
    if command == 'doctor':
        from .doctor import run_doctor
        return run_doctor(rest)
    if command == 'participant':
        if not rest or rest[0] in ('-h', '--help', 'help'):
            print('Usage: okto-nexus participant launch|remove|smoke [options]\nUse the selected action with --help for its options.')
            return 0
        if rest[0] == 'remove':
            from .participant_remove import run_participant_remove
            return run_participant_remove(rest[1:])
        if rest[0] == 'smoke':
            from .cooperation import run_cooperation
            return run_cooperation(rest[1:])
        from .participant_launch import run_participant_launch
        return run_participant_launch(rest)
    if command == 'preset':
        from .preset import run_preset
        return run_preset(rest)
    if command == 'work':
        from .work import run_work
        return run_work(rest)
    if command == 'session':
        from .session import run_session
        return run_session(rest)
    if command == 'operator':
        from .operator import run_operator
        return run_operator(rest)
    if command == "serve":
        from .serve import run_serve
        return run_serve(rest)
    if command == "service":
        from .service import run_service
        return run_service(rest)
    if command == "tail":
        from .tail import run_tail
        return run_tail(rest)
    if command == "admin":
        from .admin import run_admin
        return run_admin(rest)
    if command == "provider-credentials":
        from .provider_credentials import run_provider_credentials
        return run_provider_credentials(rest)
    # Explicit product commands above always take precedence over aliases. An
    # alias enters the same function, never a shell or a rewritten sys.argv.
    from ....application.project_preset import CLIENTS
    if command in CLIENTS:
        from .quick_connect_policy import entry_enabled
        if not entry_enabled():
            print('Quick Connect entry is disabled. Resume existing connections with connect --profile NAME.', file=sys.stderr)
            return 2
        from .connect import run_connect
        return run_connect([command, *rest])
    if command in ('stdio', 'mcp') or command.startswith('-'):
        print('MCP stdio is no longer available. Run `okto-nexus serve` and connect to its HTTP /mcp endpoint.', file=sys.stderr)
        return 2
    import difflib
    choices = ('connect', 'init', 'doctor', 'participant', 'preset', 'work', 'session',
        'operator', 'serve', 'service', 'tail', 'admin', 'observe',
        'message', 'handoff', 'request', 'provider-credentials', *CLIENTS)
    suggestions = difflib.get_close_matches(command, choices, n=3, cutoff=0.5)
    hint = (' Did you mean: ' + ', '.join(suggestions) + '?') if suggestions else ''
    print('Unknown command.' + hint + '\nUse okto-nexus --help for available commands.', file=sys.stderr)
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
