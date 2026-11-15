"""One additive READY observation after the original start failed; no start/retry."""
from pathlib import Path
import argparse
import json
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from recovery_context import RecoveryContext, require, read_json, sha
from recovery_observation import capture, same_cycle, cycle

PLAN_SHA = '8980570ab636b7836ffa34a5976652c0cc19825af015c50d50a9c5b08bcf6a27'
RETURNED_SHA = '53fdf4268ee39c680d6d9a612108e6ca91559186ce86781c564914252782b6e9'
STDOUT_SHA = '634642eb521d7a17e05661f06eb9c72fea08a8adf52ade86da97c51f51b2dab2'
RESERVED_SHA = '6d5f06cfee8244fa320d04de47764c0d618d4d993d0e5cbd513ef724c5346e1e'
GENERATION = 'a59778be231e827fdbfd95ec947e5103'
INSTANCE = 'svc_0450942fe9a6c7193b066e766742217a829264e7520801f7baa7e89469468c11'
CYCLE = '83385b0dffad1b22ee9fdd49842429ca'
IDENTITIES = {'parent': {'pid': 43100, 'birth': 134391883995944611},
              'launcher': {'pid': 54112, 'birth': 134391884090702531},
              'child': {'pid': 14264, 'birth': 134391884091386721}}


def validate_original(receipt, output):
    require(receipt.get('lifecycle_plan_sha256') == PLAN_SHA
            and type(receipt.get('returncode')) is int and receipt['returncode'] == 3
            and receipt.get('stdout_sha256') == STDOUT_SHA, 'ORIGINAL_START_RECEIPT_CHANGED')
    require(output.get('state') == 'degraded' and output.get('reason') == 'SERVICE_UNREACHABLE'
            and output.get('observation_error') == 'transient_transport'
            and output.get('observation_retryable') is True
            and output.get('ready_for_queries') is False, 'ORIGINAL_FAILURE_NOT_TRANSIENT')
    require(output.get('observed_owner') == {'instance_id': INSTANCE, 'pid': 14264,
            'generation': GENERATION}, 'ORIGINAL_OWNER_CHANGED')


def validate_current(selected):
    # Qualified capture/status validates READY; its public selection is identity-only.
    require(selected.get('pid') == 14264
            and selected.get('generation') == GENERATION and selected.get('instance_id') == INSTANCE,
            'CURRENT_READY_OWNER_CHANGED')
    cohort = selected['cohort']
    require(cohort.get('cycle_id') == CYCLE and cohort.get('phase') == 'running'
            and cohort.get('attempts_started') == 1 and cohort.get('child_acknowledged') is True,
            'CURRENT_CYCLE_CHANGED')
    require(all(cohort.get(role) == identity for role, identity in IDENTITIES.items()),
            'CURRENT_PROCESS_IDENTITIES_CHANGED')


def observe(context, *, capture_fn=capture, cycle_fn=cycle):
    require(not (context.PUBLIC/'nexus-owner-selection.json').exists()
            and not (context.PUBLIC/'late-ready-select-result.json').exists(), 'SELECTION_ALREADY_EXISTS')
    for path, expected in ((context.PUBLIC/'start-returned.json', RETURNED_SHA),
                           (context.PUBLIC/'start-reserved.json', RESERVED_SHA),
                           (context.PRIVATE/'start.stdout', STDOUT_SHA)):
        require(sha(path) == expected, 'ORIGINAL_START_BYTES_CHANGED')
    validate_original(read_json(context.PUBLIC/'start-returned.json'),
                      read_json(context.PRIVATE/'start.stdout'))
    context.save('late-ready-select-reserved.json', {'source_sha256': sha(__file__),
        'original_start_returned_sha256': RETURNED_SHA, 'original_start_stdout_sha256': STDOUT_SHA,
        'service_actions': 0, 'provider_calls': 0, 'selection': 'OBSERVE_SAME_OWNER_ONCE'})
    selected, handles = capture_fn(context)
    try:
        validate_current(selected)
        same_cycle(selected['cohort'], cycle_fn(context))
        require(not any(h.exited() for h in handles.values()), 'OWNER_EXITED_BEFORE_PUBLICATION')
        context.save('nexus-owner-selection.json', selected)
        context.save('late-ready-select-result.json', {'status': 'SAME_OWNER_READY_OBSERVED',
            'owner_selection_sha256': sha(context.PUBLIC/'nexus-owner-selection.json'),
            'original_start_returned_sha256': RETURNED_SHA, 'original_start_cli_returncode': 3,
            'original_failure_preserved': True, 'generation': GENERATION, 'cycle_id': CYCLE,
            'service_actions': 0, 'provider_calls': 0, 'restart_or_start_retry': False,
            'physical_exit_claimed': False, 'next_step': 'Separate original canonical watch selection.'})
        return {'status': 'SAME_OWNER_READY_OBSERVED', 'service_actions': 0,
                'original_start_cli_returncode': 3, 'generation': GENERATION}
    finally:
        for handle in handles.values():
            handle.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--expected-source-sha256', required=True)
    args = parser.parse_args()
    require(sha(__file__) == args.expected_source_sha256, 'SUPPLEMENT_SOURCE_CHANGED')
    context = RecoveryContext(HERE/'lifecycle-plan.json', PLAN_SHA)
    print(json.dumps(observe(context)))


if __name__ == '__main__':
    main()
