from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

from recovery_onboarding import Context, commands, preserve_old, require_rotation_before_review
from recovery_context import sha, Refused

HERE = Path(__file__).resolve().parent


class Tests(unittest.TestCase):
    def context(self):
        with patch('subprocess.Popen', side_effect=AssertionError('unexpected child')), \
             patch('httpx.Client', side_effect=AssertionError('unexpected HTTP')):
            return Context(HERE / 'draft02-plan.json', sha(HERE / 'draft02-plan.json'))

    def test_new_installed_context_and_actual_connector_parser(self):
        from okto_nexus_connector.cli.main import build_parser
        X = self.context()
        discover, create, review, answers = commands(X)
        parsed = build_parser().parse_args(create[create.index('-m') + 2:])
        self.assertEqual(parsed.request_id, 'm1-sonnet-remote-setup-02')
        self.assertEqual(parsed.binding_alias, 'm1-sonnet-remote-recovery02')
        self.assertEqual(parsed.agent, 'm1-sonnet-remote')
        self.assertFalse(parsed.credential_stdin)
        self.assertIsNone(parsed.credential_env)
        self.assertFalse(parsed.start_at_login)
        self.assertEqual(discover[-2:], ['--harness', 'claude_stream'])
        self.assertNotIn('--new-agent', review)
        self.assertEqual(review[review.index('--workspace-id') + 1], X.P['workspace_id'])
        self.assertEqual(review[review.index('--agent') + 1], X.P['agent_id'])
        self.assertIn('--plan', review)
        self.assertEqual(len(answers.splitlines()), 9)

    def test_installed_schema_keeps_same_sonnet_permissions_and_limits(self):
        from nexus_connector_core import discover_harness_configuration
        from okto_nexus_connector.cli.commands.configure import template
        from okto_nexus_connector.cli.wizard_prompts import preferences, choice
        X = self.context()
        values = iter(commands(X)[3].splitlines())
        with patch('builtins.input', side_effect=lambda: next(values)):
            cfg = preferences(template(), discover_harness_configuration('claude_stream'))
            self.assertTrue(choice('Save draft?', [(True, 'Save'), (False, 'Cancel')], False))
        self.assertEqual(cfg['harness_settings'], {'model': 'sonnet', 'permission_mode': 'default', 'inherit_global_mcps': 'disabled'})
        self.assertEqual(cfg['authorization'], {'minutes': 60, 'actions': 3, 'no_expiry': False, 'unlimited_actions': False})
        self.assertEqual((cfg['session_policy'], cfg['tool_access']), ('per_sender', 'ask'))
        with self.assertRaises(StopIteration):
            next(values)

    def test_old_setup_preservation_and_stale_plan_refusal(self):
        before = {'draft': {'setup_run_id': 'setup01'}, 'stage': 'awaiting_host'}
        preserve_old(before, deepcopy(before))
        with self.assertRaisesRegex(Refused, 'OLD_SETUP_CHANGED'):
            preserve_old(before, dict(before, stage='configured'))
        with self.assertRaisesRegex(Refused, 'DRAFT_PLAN_CHANGED'):
            Context(HERE / 'draft02-plan.json', '0' * 64)

    def test_future_review_cannot_promote_failed_transfer_or_wrong_epoch(self):
        p = {'agent_id': 'agent', 'server_id': 'server'}
        t = dict(status='TRANSFERRED_ONCE', producer_exit=0, consumer_exit=0,
                 active_job_processes_after=0, forced_owned_cleanup=False,
                 public_ipc_readers_joined=True, effect_guard_required=True,
                 effect_gates_allowed=['producer', 'consumer'])
        value = dict(status='ROTATED_ONCE_IMPORTED_ONCE', agent_id='agent', server_id='server',
                     old_epoch=1, current_epoch=2, rotation_post_count=1, consumer_count=1,
                     original_transfer_preserved_unconfirmed=True, old_profile_replayed=False,
                     protected_transfer=t)
        require_rotation_before_review(value, p)
        for key, wrong in [('status', 'UNCONFIRMED'), ('current_epoch', 1), ('agent_id', 'new-agent'),
                           ('rotation_post_count', True), ('old_profile_replayed', True)]:
            with self.assertRaises(Refused):
                require_rotation_before_review(dict(value, **{key: wrong}), p)
        with self.assertRaises(Refused):
            require_rotation_before_review(dict(value, protected_transfer=dict(t, consumer_exit=1)), p)


if __name__ == '__main__':
    unittest.main(verbosity=2)
