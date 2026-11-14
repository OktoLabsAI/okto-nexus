"""One finite wrapper selection, durably reserved before Popen; never replay."""
from pathlib import Path
import json
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from driver_common import FINITE_CHOICES as CHOICES
from driver_common import gate, main_guard, parser, private_outputs, read_json, require, reserve, sha, tags


def select(context, mode, selection):
    require(mode in CHOICES and tuple(selection) in CHOICES[mode], 'FINITE_SELECTION_INVALID')
    key = ('planning_commands' if mode == 'plan' else 'root_driver_' + mode
        if mode in ('operator_bootstrap', 'adopt_local', 'authorize_local') else mode)
    entry = context.P['execution_bundle']['files'][key]
    require(sha(entry['path']) == entry['sha256'], 'SELECTED_MODULE_CHANGED')
    if mode == 'plan':
        command = read_json(entry['path'])[selection[0]]
        return command['argv'], command.get('nonsecret_stdin')
    return [context.P['package_pins']['python'], '-I', '-B', entry['path'],
        *context.common_args(), *selection], None


def dispatch(context, mode, selection, directory, *, popen=subprocess.Popen):
    argv, stdin_value = select(context, mode, selection)
    name = '-'.join([mode, *selection])
    require(all(isinstance(s, str) for s in argv) and '--force' not in argv, 'COMMAND_INVALID')
    require(argv[0] == context.P['package_pins']['python'], 'INTERPRETER_CHANGED')
    reserve(directory / (name + '.reserved.json'), {**tags(context), 'mode': mode,
        'selection': selection, 'selected_at': time.time(), 'state': 'DISPATCH_RESERVED'})
    # A spawn failure still consumes this outer selection. The canonical wrapper
    # keeps its own effect reservation; neither layer grants a second dispatch.
    with (directory / (name + '.stdout')).open('xb') as stdout, (directory / (name + '.stderr')).open('xb') as stderr:
        child = popen(argv, cwd=directory, env=context.env(), stdout=stdout, stderr=stderr,
            stdin=subprocess.PIPE if stdin_value is not None else subprocess.DEVNULL,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        reserve(directory / (name + '.process.json'), {**tags(context), 'pid': child.pid,
            'mode': mode, 'selection': selection, 'created_at': time.time()})
        if stdin_value is not None:
            child.communicate(stdin_value.encode('utf-8'))
        code = child.wait()  # retained wrapper handle; never timeout-kill
    result = {**tags(context), 'mode': mode, 'selection': selection, 'returncode': code,
        'wrapper_exit_confirmed': True, 'completed_at': time.time(),
        'stdout_sha256': sha(directory / (name + '.stdout')), 'stderr_sha256': sha(directory / (name + '.stderr'))}
    reserve(directory / (name + '.returned.json'), result)
    return result


def main():
    p = parser()
    p.add_argument('mode', choices=CHOICES)
    p.add_argument('selection', nargs='+')
    args = p.parse_args()
    context = gate(args)
    require(args.mode in CHOICES and tuple(args.selection) in CHOICES[args.mode], 'FINITE_SELECTION_INVALID')
    if (args.mode, args.selection) != ('lifecycle', ['initialize']):
        from driver_common import require_tags
        require_tags(read_json(context.PUBLIC / 'root-driver-preparation.json'), context)
    result = dispatch(context, args.mode, args.selection, private_outputs())
    print(json.dumps(result), flush=True)
    return result['returncode']


if __name__ == '__main__':
    raise SystemExit(main_guard(main))
