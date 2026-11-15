"""Additive repair of campaign nexus label versus canonical server component.

Never reruns upgrade-plan and never rewrites the original source or reservation.
"""
from pathlib import Path
import argparse
import copy
import json
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from recovery_context import RecoveryContext, require, read_json, sha, pin
import recovery_lifecycle as frozen


def validate_server_plan(context, document):
    require(document['plan']['component'] == 'server', 'CANONICAL_SERVER_COMPONENT_REQUIRED')
    # Adapter changes only the validation label in a disposable copy. The raw
    # canonical document and its revision remain untouched for product apply.
    validation_copy = copy.deepcopy(document)
    validation_copy['plan']['component'] = 'nexus'
    result = frozen.validate_upgrade(context, 'nexus', validation_copy)
    return dict(result, component='server', campaign_component='nexus')


def reconcile(context, compat_sha):
    original = read_json(context.PUBLIC / 'nexus-upgrade-plan-reserved.json')
    context.require_tags(original)
    require(original['argv'] == frozen.upgrade_argv(context, 'nexus', 'upgrade-plan'), 'ORIGINAL_PLAN_COMMAND_CHANGED')
    document_path = context.PRIVATE / 'nexus-upgrade-plan.json'
    output_path = context.PRIVATE / 'nexus-upgrade-plan.stdout'
    document, output = read_json(document_path), read_json(output_path)
    require(output == document, 'ORIGINAL_STDOUT_DOCUMENT_MISMATCH')
    review = validate_server_plan(context, document)
    frozen.task_absent(context, 'nexus')
    require(not (context.PUBLIC / 'nexus-upgrade-plan-returned.json').exists(), 'ORIGINAL_RETURN_RECEIPT_EXISTS')
    value = {'status': 'CANONICAL_PLAN_RECONCILED_ORIGINAL_WRAPPER_FAILED',
             'document_sha256': sha(document_path), 'stdout_sha256': sha(output_path),
             'original_reservation_sha256': sha(context.PUBLIC / 'nexus-upgrade-plan-reserved.json'),
             'compat_sha256': compat_sha, 'review': review,
             'original_wrapper': {'exit_code': 1, 'code': 'UPGRADE_SCOPE_CHANGED', 'root_tool': 'db7921'},
             'child_exit_code_derived_from_frozen_control_flow': 0,
             'direct_child_exit_receipt_available': False,
             'child_exit_evidence': 'Derived from frozen migration control flow and root tool db7921: validate_upgrade is invoked only inside returncode==0; UPGRADE_SCOPE_CHANGED is its exact first failed guard. No original returned receipt was written.',
             'upgrade_plan_reexecuted': False, 'apply_selected': False, 'provider_calls': 0}
    context.save('nexus-upgrade-plan-reconciled.json', value)
    return value


def apply(context, compat_sha, revision):
    previous = read_json(context.PUBLIC / 'nexus-upgrade-plan-reconciled.json')
    context.require_tags(previous)
    require(previous['compat_sha256'] == compat_sha, 'RECONCILIATION_SOURCE_CHANGED')
    document_path = context.PRIVATE / 'nexus-upgrade-plan.json'
    require(sha(document_path) == previous['document_sha256'], 'RECONCILED_PLAN_CHANGED')
    document = read_json(document_path)
    validate_server_plan(context, document)
    require(revision == document['plan_revision'], 'EXPLICIT_REVIEW_REVISION_CHANGED')
    frozen.task_absent(context, 'nexus')
    for item in context.installed['files']:
        pin(item)
    value = frozen.run_cli(context, 'nexus', 'upgrade-apply',
                           frozen.upgrade_argv(context, 'nexus', 'upgrade-apply', revision))
    value['compat_sha256'] = compat_sha
    value['canonical_component'] = 'server'
    if value['returncode'] == 0:
        require(value['projection'].get('applied') is True, 'UPGRADE_NOT_CONFIRMED')
        actual = read_json(context.P['source_contexts']['nexus']['path'])
        require(actual == document['plan']['target_context'], 'APPLIED_CONTEXT_NOT_EXACT_TARGET')
        frozen.task_absent(context, 'nexus')
        value['target_context_sha256'] = sha(context.P['source_contexts']['nexus']['path'])
    context.save('nexus-upgrade-apply-returned.json', value)
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan', required=True)
    parser.add_argument('--expected-plan-sha256', required=True)
    parser.add_argument('--expected-compat-sha256', required=True)
    parser.add_argument('--upgrade-revision')
    parser.add_argument('action', choices=('reconcile-plan', 'upgrade-apply'))
    args = parser.parse_args()
    require(sha(__file__) == args.expected_compat_sha256, 'COMPAT_SOURCE_CHANGED')
    require(bool(args.upgrade_revision) == (args.action == 'upgrade-apply'), 'EXPLICIT_REVISION_REQUIRED_ONLY_FOR_APPLY')
    context = RecoveryContext(args.plan, args.expected_plan_sha256)
    value = (reconcile(context, args.expected_compat_sha256) if args.action == 'reconcile-plan'
             else apply(context, args.expected_compat_sha256, args.upgrade_revision))
    print(json.dumps(value))
    return 0 if value.get('returncode', 0) == 0 else 3


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        print(json.dumps({'status': 'SERVER_COMPONENT_COMPAT_UNCONFIRMED', 'error_type': type(error).__name__}))
        raise SystemExit(3) from None
