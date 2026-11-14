"""Runtime preparation after initialize, before setup or service installation."""
from pathlib import Path
import json
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from driver_common import gate, main_guard, parser, private_outputs, public_save, require, secure_directory


def main():
    context = gate(parser().parse_args())
    require(context.CONTROL.is_dir() and context.PUBLIC.is_dir() and context.PRIVATE.is_dir(), 'INITIALIZE_FIRST')
    require(not (context.PUBLIC / 'root-driver-preparation.json').exists(), 'PREPARATION_ALREADY_RECORDED')
    require(not any((context.PUBLIC).glob('lifecycle-*-install.json')), 'PREPARE_BEFORE_SERVICE_INSTALL')
    require(not (context.PRIVATE / 'controller.json').exists(), 'PREPARE_BEFORE_CONTROLLER')
    private_outputs()
    # Retained predecessor homes are immutable to preparation; protect only the
    # new private control evidence and this driver's own runtime capture.
    secure_directory(context.PRIVATE, context.CONTROL)
    result = {'status': 'OWN_DIRECTORIES_ACL_PREPARED', 'prepared_at': time.time(),
        'provider_accessed': False, 'controller_created': False, 'service_action': False}
    public_save(context, 'root-driver-preparation.json', result)
    print(json.dumps(result))
    return 0


if __name__ == '__main__':
    raise SystemExit(main_guard(main))
