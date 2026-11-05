"""An operator decides on their own client; the Connector only observes proof."""
import argparse
import json
import os
from pathlib import Path
import sys

from ....application.terminal_binding_approval import TerminalBindingApproval
from ....application.terminal_connection import ConnectionError
from ....config import load_config
from ...outbound.operator_client import OperatorProfile
from .native_input import display_text


def display_review(review):
    proposal = review['proposal']
    print('Approval: ' + display_text(review['approval_id']) + ' | ' + display_text(review['status']))
    print('Agent: ' + display_text(review['agent_id']) + ' | Workspace: ' + display_text(review['workspace_id']))
    print('Execution host: ' + display_text(proposal['executor_id']))
    print('Harness: ' + display_text(proposal['adapter_id']) + ' | Installation: ' + display_text(proposal['candidate_ref']))
    print('Proposal: ' + display_text(proposal['proposal_id']) + f" revision {proposal['proposal_revision']}")
    print('Expires: ' + display_text(proposal['expires_at']) + (' (expired)' if review['expired'] else ''))
    print(display_text(proposal['diff']['summary']))
    print('Review: ' + display_text(review['review_revision']))
    print('Approval lets the original Connector apply this scope. It does not submit project work.')


def run_operator_approval(argv):
    parser = argparse.ArgumentParser(prog='okto-nexus operator approval')
    parser.add_argument('approval_id')
    parser.add_argument('--profile', required=True, help='human operator profile on this client')
    parser.add_argument('--home', type=Path)
    parser.add_argument('--decision', choices=('approve', 'reject'))
    parser.add_argument('--confirm', help='exact review revision for noninteractive decision')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    if args.confirm and not args.decision:
        parser.error('--confirm requires --decision')
    try:
        client = OperatorProfile(args.home or load_config(os.environ, []).home_dir, args.profile).client()
        client.verify()
        flow = TerminalBindingApproval(client)
        review = flow.review(args.approval_id)
        if not args.decision:
            print(json.dumps(review, ensure_ascii=False)) if args.json else display_review(review)
            return 0
        revision = args.confirm
        if revision is None:
            if args.json or not sys.stdin.isatty():
                raise ConnectionError('REVIEW_REQUIRED', 'Inspect this approval, then pass --confirm with its exact review revision.')
            display_review(review)
            if input('Confirm ' + args.decision + ' for this exact request? [yes/no] ').strip().lower() != 'yes':
                print('Decision canceled.')
                return 0
            revision = review['review_revision']
        result = flow.decide(args.approval_id, args.decision, revision)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (EOFError, KeyboardInterrupt):
        return 130
    except (ConnectionError, OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps(dict(state='unconfirmed', approval_id=args.approval_id,
            code=getattr(error, 'code', 'OPERATOR_APPROVAL_UNAVAILABLE'),
            message=getattr(error, 'message', 'Inspect the selected operator profile and canonical approval.'),
            possible_effect=getattr(error, 'possible_effect', False),
            recovery='Inspect this same approval ID; do not create another Connector proposal.')))
        return 3
