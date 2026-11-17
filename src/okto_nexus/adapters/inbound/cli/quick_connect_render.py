"""Render an unexecuted resume vector for an explicitly named shell."""
import shlex


def public_resume_argv(argv, *, execution_location):
    """Hide the technical shortcut only when exact public selectors replace it."""
    # annotate's connected vector has four positional values, including the
    # logical project label. That label may itself equal an option name. Omit it
    # from the basic command: exact workspace/binding selectors identify it.
    if len(argv) < 4 or argv[1] != 'connect' or (len(argv) - 4) % 2:
        raise ValueError('The connected resume vector is incomplete.')
    options = {}
    allowed = ('--profile', '--home', '--id', '--project', '--operator-profile', '--workspace-id', '--binding-id')
    for index in range(4, len(argv), 2):
        flag, value = argv[index:index + 2]
        if flag not in allowed or flag in options or not isinstance(value, str) or not value:
            raise ValueError('Exact resume selectors are unavailable.')
        options[flag] = value
    required = ('--home', '--workspace-id', '--binding-id')
    required += ('--operator-profile',) if execution_location == 'remote' else ('--project',)
    for flag in required:
        if flag not in options:
            raise ValueError('Exact resume selectors are unavailable.')
    if execution_location == 'remote' and '--project' in options:
        raise ValueError('A remote resume must not carry an execution-host path.')
    if execution_location not in ('local', 'remote'):
        raise ValueError('The resume topology is unconfirmed.')
    result = list(argv[:3])
    for flag, value in options.items():
        if flag != '--profile':
            # Shell quoting does not change argparse's option recognition.
            result.extend((flag + '=' + value,) if value.startswith('-') else (flag, value))
    return tuple(result)


def render_resume_command(argv, *, shell):
    """No subprocess, evaluation, filesystem lookup or shell autodiscovery."""
    if not argv or any(not isinstance(value, str) or any(c in value for c in '\x00\r\n') for value in argv):
        raise ValueError('Resume arguments must be single-line strings without NUL.')
    if shell == 'posix':
        return shlex.join(argv)
    if shell == 'powershell':
        # PS 5.1's native argument binder loses quotes/empty arguments. Require
        # the modern binder explicitly, in a child scope, before any invocation.
        literals = ' '.join("'" + value.replace("'", "''") + "'" for value in argv)
        return ("& { if ($PSVersionTable.PSVersion -lt [version]'7.3') { "
                "throw 'Use PowerShell 7.3+ or the JSON resume_argv array.' }; "
                "$PSNativeCommandArgumentPassing = 'Standard'; & " + literals + ' }')
    raise ValueError('Choose POSIX sh or PowerShell 7.3+ explicitly.')
