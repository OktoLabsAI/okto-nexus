"""Additive CLI argument-name compatibility; frozen rotation effects unchanged."""
from pathlib import Path
import argparse
import hashlib
import importlib
import json
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
ORIGINALS = {
    'rotation_executor.py': 'a038e1f4ff6b614d8f9d4cb598ce687735070b7339e43f7730e459af49cf7cb1',
    'rotation_producer.py': '6e3f548810135082ccbcc0484342393c8d280aa87319824308deea43abec95a4'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(value, code):
    if not value:
        raise RuntimeError(code)


def load_context(executor, producer=False, argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan', required=True)
    parser.add_argument('--expected-plan-sha256', required=True)
    parser.add_argument('--authorization-sha256', required=True)
    if not producer:
        parser.add_argument('action', choices=('approve-storage', 'transfer'))
    args = parser.parse_args(argv)
    context = executor.Context(args.plan, args.expected_plan_sha256, args.authorization_sha256)
    context.action = getattr(args, 'action', None)
    return context


def adapt_transfer(context, transfer_once, original_transfer, compat_sha):
    def adapter(**kwargs):
        argv = list(kwargs['producer_argv'])
        original = context.P['runtime_pins']['rotation_producer.py']
        require(Path(original['path']).resolve() == HERE/'rotation_producer.py'
                and original['sha256'] == ORIGINALS['rotation_producer.py']
                and sha(original['path']) == original['sha256'], 'ORIGINAL_PRODUCER_CHANGED')
        require(len(argv) >= 6 and argv[1:5] == ['-I', '-B', '-X', 'utf8']
                and Path(argv[5]).resolve() == HERE/'rotation_producer.py', 'PRODUCER_ARGV_CHANGED')
        require(sha(__file__) == compat_sha, 'COMPAT_SOURCE_CHANGED')
        kwargs['producer_argv'] = argv[:5] + [str(Path(__file__).resolve()), '--producer',
            '--expected-compat-sha256', compat_sha] + argv[6:]
        return transfer_once(**kwargs)
    return original_transfer(context, adapter)


def sources():
    for name, expected in ORIGINALS.items():
        require(sha(HERE/name) == expected, 'FROZEN_ORIGINAL_CHANGED')
    return importlib.import_module('rotation_executor'), importlib.import_module('rotation_producer')


def main(argv=None):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--producer', action='store_true')
    parser.add_argument('--expected-compat-sha256', required=True)
    args, remaining = parser.parse_known_args(argv)
    require(sha(__file__) == args.expected_compat_sha256, 'COMPAT_SOURCE_CHANGED')
    executor, producer = sources()
    old_load, old_transfer, old_argv = executor.load_context, executor.transfer, sys.argv
    try:
        executor.load_context = lambda producer=False: load_context(executor, producer)
        executor.transfer = lambda context, fn: adapt_transfer(context, fn, old_transfer, args.expected_compat_sha256)
        sys.argv = [str(Path(__file__).resolve()), *remaining]
        return producer.main() if args.producer else executor.main()
    finally:
        executor.load_context, executor.transfer, sys.argv = old_load, old_transfer, old_argv


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        print(json.dumps({'status': 'ROTATION_COMPAT_UNCONFIRMED',
                          'error_type': type(error).__name__, 'automatic_retry': False}))
        raise SystemExit(3) from None
