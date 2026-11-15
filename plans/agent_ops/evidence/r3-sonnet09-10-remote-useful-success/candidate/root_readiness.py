"""Root's explicit readiness acknowledgement; no decision, API or service action."""
from datetime import datetime, timezone
from pathlib import Path
import argparse, hashlib, json, os, sys, uuid

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from fast_approval import read, require, stamp, digest, exclusive


def acknowledgement(public, view, *, request, operation, session, approval, revision, command_hash, now):
    require(public.get('native_pending_count') == 1, 'ONE_NATIVE_QUESTION_REQUIRED')
    fields = ('request_id', 'operation_id', 'scope', 'approval_id', 'review_revision',
              'command_sha256', 'expires_at', 'observed_utc', 'tool_name')
    require(all(public.get(k) == view.get(k) for k in fields), 'PUBLIC_ROOT_VIEW_CHANGED')
    scope = public.get('scope')
    require(isinstance(scope, dict) and scope.get('session_id') == session, 'SESSION_CHANGED')
    require(public.get('request_id') == request and public.get('operation_id') == operation
            and public.get('approval_id') == approval and public.get('review_revision') == revision,
            'QUESTION_IDENTITY_CHANGED')
    require(isinstance(view.get('command'), str)
            and public.get('command_sha256') == command_hash == digest(view['command']),
            'REVIEWED_COMMAND_CHANGED')
    require(0 <= (now - stamp(public['observed_utc'])).total_seconds() <= 20,
            'QUESTION_OBSERVATION_STALE')
    require((stamp(public['expires_at']) - now).total_seconds() >= 30,
            'QUESTION_EXPIRED_OR_TOO_LATE')
    return dict(scope), {'manually_ready': True, 'model_pending': False,
        'request_id': request, 'operation_id': operation, 'session_id': session,
        'approval_id': approval, 'review_revision': revision,
        'command_sha256': command_hash, 'observed_utc': now.isoformat(),
        'expires_at': public['expires_at'], 'decision_sent': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('expected-request', 'expected-operation', 'expected-session',
                 'expected-approval', 'expected-revision', 'reviewed-command-sha256'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    private = HERE / 'paid-work/private'
    public_path = HERE / 'paid-work/public/fast-native-question.json'
    view_path = private / 'native-command-root-view.json'
    scope, ready = acknowledgement(read(public_path), read(view_path),
        request=args.expected_request, operation=args.expected_operation,
        session=args.expected_session, approval=args.expected_approval,
        revision=args.expected_revision, command_hash=args.reviewed_command_sha256,
        now=datetime.now(timezone.utc))
    scope_path = private / 'native-scope.json'
    if scope_path.exists():
        require(read(scope_path) == scope, 'PRIOR_SCOPE_CHANGED')
    else:
        exclusive(scope_path, scope)
    ready_path = private / 'root-manually-ready.json'
    if ready_path.exists():
        old = read(ready_path)
        require(all(old.get(k) == ready[k] for k in
                    ('request_id', 'operation_id', 'session_id', 'approval_id',
                     'review_revision', 'command_sha256')), 'PRIOR_READINESS_CHANGED')
    temporary = private / ('root-readiness-' + uuid.uuid4().hex + '.writing')
    exclusive(temporary, ready)
    os.replace(temporary, ready_path)
    print(json.dumps({'status': 'ROOT_READINESS_RECORDED_NO_DECISION',
        'request_id': ready['request_id'], 'approval_id': ready['approval_id'],
        'command_sha256': ready['command_sha256'], 'decision_sent': False,
        'next': 'Wait for public root_model_pending=false, then select approve or deny explicitly.'}))


if __name__ == '__main__':
    main()
