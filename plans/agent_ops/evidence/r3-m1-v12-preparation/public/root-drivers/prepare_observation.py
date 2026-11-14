"""Runtime preparation after initialize, before setup or service installation."""
from pathlib import Path
import json
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from driver_common import gate, main_guard, parser, private_outputs, public_save, require, secure_directory


def main():
    context = gate(parser().parse_args())
    require(context.ROOT.is_dir(), 'INITIALIZE_FIRST')
    require(not (context.ROOT / 'public/root-driver-preparation.json').exists(), 'PREPARATION_ALREADY_RECORDED')
    require(not any((context.ROOT / 'public').glob('lifecycle-*-install.json')), 'PREPARE_BEFORE_SERVICE_INSTALL')
    require(not (context.ROOT / 'private/controller.json').exists(), 'PREPARE_BEFORE_CONTROLLER')
    private_outputs()
    for path in sorted({Path(v) for k, v in context.P['paths'].items() if k != 'codex_executable'}, key=lambda p: len(p.parts)):
        require(path.is_dir(), 'INITIALIZED_DIRECTORY_MISSING')
        secure_directory(path, context.ROOT)
    result = {'status': 'OWN_DIRECTORIES_ACL_PREPARED', 'prepared_at': time.time(),
        'provider_accessed': False, 'controller_created': False, 'service_action': False}
    public_save(context, 'root-driver-preparation.json', result)
    print(json.dumps(result))
    return 0


if __name__ == '__main__':
    raise SystemExit(main_guard(main))
