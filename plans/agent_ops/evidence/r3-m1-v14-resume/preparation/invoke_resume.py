"""One finite, durably reserved wrapper launch in the resume evidence ledger."""
from pathlib import Path
import json
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from resume_context import HERE, gate, parser, python_utf8, require


def dispatch(context, mode, selection, *, popen=subprocess.Popen):
    common = context.common
    choices = {'lifecycle': [('nexus', action) for action in ('install', 'start', 'stop', 'uninstall')],
               'work': [('local', phase) for phase in ('useful', 'continuation')]}
    require(mode in choices and tuple(selection) in choices[mode], 'FINITE_SELECTION_INVALID')
    require((context.PUBLIC / 'root-driver-preparation.json').is_file(), 'PREPARE_FIRST')
    directory = common.private_outputs()
    name = '-'.join([mode, *selection])
    argv = python_utf8([context.P['package_pins']['python'], '-I', '-B', str(HERE / 'resume_entry.py'),
        *context.common_args(), mode, *selection], context.P['package_pins']['python'])
    require(argv[0] == context.P['package_pins']['python'] and '--force' not in argv, 'COMMAND_CHANGED')
    common.reserve(directory / (name + '.reserved.json'), {**common.tags(context),
        'mode': mode, 'selection': selection, 'state': 'DISPATCH_RESERVED', 'selected_at': time.time()})
    with (directory / (name + '.stdout')).open('xb') as stdout, (directory / (name + '.stderr')).open('xb') as stderr:
        child = popen(argv, cwd=directory, env=context.env(), stdout=stdout, stderr=stderr,
            stdin=subprocess.DEVNULL,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        common.reserve(directory / (name + '.process.json'), {**common.tags(context),
            'pid': child.pid, 'mode': mode, 'selection': selection, 'created_at': time.time()})
        code = child.wait()  # retained handle; no timeout-kill or replay
    result = {**common.tags(context), 'mode': mode, 'selection': selection,
        'returncode': code, 'wrapper_exit_confirmed': True, 'completed_at': time.time(),
        'stdout_sha256': common.sha(directory / (name + '.stdout')),
        'stderr_sha256': common.sha(directory / (name + '.stderr'))}
    common.reserve(directory / (name + '.returned.json'), result)
    return result


def main():
    args, remaining = parser().parse_known_args()
    require(bool(remaining), 'MODE_REQUIRED')
    result = dispatch(gate(args), remaining[0], remaining[1:])
    print(json.dumps(result), flush=True)
    return result['returncode']


if __name__ == '__main__':
    raise SystemExit(main())
