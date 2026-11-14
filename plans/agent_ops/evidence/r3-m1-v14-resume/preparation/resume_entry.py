"""Run one pinned original entrypoint with the explicitly derived v14 context."""
from pathlib import Path
import json
import runpy
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from resume_context import gate, parser, pinned, prepare, require

MODES = {
    'lifecycle': 'lifecycle', 'work': 'work',
    'observation': 'root_driver_observation', 'cleanup': 'root_driver_confirm_cleanup',
    'final_presence': 'root_driver_confirm_final_presence', 'close': 'root_driver_close_campaign',
}


def execute(context, mode, selection, *, run=runpy.run_path):
    if mode == 'prepare':
        require(not selection, 'PREPARE_SELECTION_INVALID')
        return prepare(context)
    require(mode in MODES, 'FINITE_MODE_INVALID')
    require((context.PUBLIC / 'root-driver-preparation.json').is_file(), 'PREPARE_FIRST')
    if mode == 'lifecycle':
        require(len(selection) == 2 and selection[0] == 'nexus'
            and selection[1] in ('install', 'start', 'stop', 'uninstall'), 'FINITE_LIFECYCLE_INVALID')
    if mode == 'work':
        require(tuple(selection) in (('local', 'useful'), ('local', 'continuation')), 'LOCAL_RESUME_ONLY')
    if mode in ('observation', 'cleanup'):
        require(selection and selection[0] == 'nexus', 'LOCAL_RESUME_ONLY')
    entry = context.amendment['sources']['work'] if mode == 'work' else context.P['execution_bundle']['files'][MODES[mode]]
    path = pinned(entry)
    context.remaining = selection
    # Imports from the original entry directory may resolve original helpers,
    # whose source pins have all been verified by the unchanged v14 gate.
    sys.path.insert(0, str(path.parent))
    sys.path.insert(0, str(context.modules))
    previous = sys.argv
    try:
        sys.argv = [str(path), *context.common_args(), *selection]
        run(str(path), run_name='__main__')
        return 0
    except SystemExit as error:
        return int(error.code or 0)
    finally:
        sys.argv = previous


def main():
    args, remaining = parser().parse_known_args()
    require(bool(remaining), 'MODE_REQUIRED')
    context = gate(args)
    return execute(context, remaining[0], remaining[1:])


if __name__ == '__main__':
    try:
        code = main()
    except Exception as error:
        print(json.dumps({'status': 'REFUSED_OR_UNCONFIRMED', 'code': type(error).__name__}), flush=True)
        raise
    raise SystemExit(code)
