"""Explicit root-selected single lifecycle action; never paid work."""
from pathlib import Path
import argparse
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from recovery_context import RecoveryContext, Refused
from recovery_lifecycle import dispatch


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan', required=True)
    parser.add_argument('--expected-plan-sha256', required=True)
    parser.add_argument('--upgrade-revision')
    parser.add_argument('component', choices=('both', 'nexus', 'connector'))
    parser.add_argument('action', choices=('prepare', 'upgrade-plan', 'upgrade-apply', 'install',
                                         'start', 'select', 'watch', 'stop', 'cleanup', 'uninstall'))
    args = parser.parse_args()
    if bool(args.upgrade_revision) != (args.action == 'upgrade-apply'):
        parser.error('Only upgrade-apply requires --upgrade-revision.')
    context = RecoveryContext(args.plan, args.expected_plan_sha256)
    value = dispatch(context, args.component, args.action, args.upgrade_revision)
    print(json.dumps(value, ensure_ascii=False))
    return 0 if value.get('returncode', 0) == 0 else 3


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        print(json.dumps({'status': 'RECOVERY_LIFECYCLE_UNCONFIRMED',
                          'code': str(error) if isinstance(error, Refused) else type(error).__name__,
                          'model_admissions': 0, 'force_used': False}))
        raise SystemExit(3) from None
