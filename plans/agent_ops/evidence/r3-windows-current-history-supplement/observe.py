"""Before/after manual Windows events on the real M1 homes. No lifecycle controls."""
from pathlib import Path
import argparse
import hashlib
import json
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import history

def load():
    plan = json.loads((HERE / 'plan.json').read_bytes())
    history.require(Path(sys.prefix).resolve() == Path(plan['python_prefix']).resolve(), 'INSTALLED_PREFIX_CHANGED')
    for pin in plan['read_only_dependencies']:
        history.require(hashlib.sha256(Path(pin['path']).read_bytes()).hexdigest() == pin['sha256'], 'DEPENDENCY_CHANGED')
    sys.path.insert(0, plan['observer_sources'])
    import event_native
    import event_observer
    return plan, event_native, event_observer

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('history-now', 'before', 'after', 'assess'))
    parser.add_argument('--event', choices=('01-suspend-resume', '02-sign-out-logon', '03-shutdown-power-on-logon', '04-restart-logon'))
    parser.add_argument('--actual-marker')
    args = parser.parse_args()
    P, N, O = load()
    if args.action == 'history-now':
        value = history.capture(P)
        O.save(HERE / 'history-current.json', value)
        print(json.dumps({'status': value['status'], 'databases': len(value['databases']), 'provider_calls': 0}))
        return
    history.require(args.event is not None, 'EVENT_REQUIRED')
    directory = HERE / 'evidence' / args.event
    directory.mkdir(parents=True, exist_ok=True)
    if args.action == 'before':
        # Read facts now, never substitute a historical READY or expired watcher.
        value, handles = N.snapshot(P, retain=True)
        try:
            history.require(all(O.ready(value['components'][n]) for n in ('nexus', 'connector')),
                            'BOTH_READY_CURRENT_SIX_HANDLES_REQUIRED')
            history.require(len(handles) == 6 and not value['own_session'].get('unconfirmed'), 'SIX_HANDLES_AND_LOGON_REQUIRED')
            for name in ('nexus', 'connector'):
                history.require(value['components'][name]['task']['digest'] == P['task_digests'][name], 'TASK_DEFINITION_CHANGED')
            state = history.capture(P)
            history.require(not any(h.exited() for h in handles.values()), 'OWNER_EXIT_DURING_HISTORY_READ')
            for name in ('nexus', 'connector'):
                current = N.canonical_status(P, name)
                original = value['components'][name]['canonical']
                history.require(all(current.get(k) == original.get(k) for k in ('pid', 'generation', 'instance_id'))
                                and current.get('state') == 'ready' and current.get('ready_for_queries') is True,
                                'OWNER_CHANGED_DURING_HISTORY_READ')
            value.update(event_id=args.event, plan_sha256=O.digest(HERE / 'plan.json'),
                         invocation_inventory=O.invocation_inventory(HERE), event_action_selected=False,
                         history=state, prior_lifecycle_errors_preserved=True)
            before_sha = O.save(directory / 'before.json', value)
            print(json.dumps({'status': 'BEFORE_DURABLE_READY_FOR_MANUAL_EVENT', 'event_id': args.event,
                              'before_sha256': before_sha}), flush=True)
            O.retained_watch(P, args.event, value, handles, before_sha)
            handles = {}
        finally:
            for h in handles.values():
                h.close()
    elif args.action == 'after':
        history.require(args.actual_marker is not None, 'ACTUAL_MANUAL_EVENT_MARKER_REQUIRED')
        # Historical O.after publishes the actual event/native observation;
        # the separate history projection cannot overwrite either observation.
        result = O.after(P, args.event, O.read(args.actual_marker))
        O.save(directory / 'history-after.json', history.capture(P))
        print(json.dumps({'status': 'AFTER_RECORDED', 'event_id': args.event, 'provider_calls': 0}))
    else:
        old, new = O.read(directory / 'before.json'), O.read(directory / 'after.json')
        retained = O.read(directory / 'retained-final.json') if (directory / 'retained-final.json').exists() else None
        assessment = O.assess(old, new, O.digest(directory / 'before.json'), retained)
        assessment['history'] = history.compare(old['history'], O.read(directory / 'history-after.json'))
        assessment['scope'] = 'KNOWN_REAL_HISTORY_NO_NEW_ADMISSION'
        assessment['acceptance_automatically_promoted'] = False
        assessment['manual_start_inventory_covers_only_this_helper'] = True
        O.save(directory / 'assessment.json', assessment)
        print(json.dumps({'status': assessment['history']['status'], 'event_id': args.event, 'provider_calls': 0}))

if __name__ == '__main__':
    main()
