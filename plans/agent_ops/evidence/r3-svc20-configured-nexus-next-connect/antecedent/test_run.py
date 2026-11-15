import copy
import json
from pathlib import Path
import unittest
import run

PLAN = json.loads((Path(__file__).parent / 'plan.json').read_bytes())


class CompletedProfileCut(unittest.TestCase):
    def fixture(self):
        p = PLAN['nexus']['profile_selection']
        return {'state': 'done', 'server_id': p['server_id'],
                'selection': {'agent': p['agent_id'], 'project': p['project']},
                'result': {'saved': True, 'binding': {'binding_id': p['binding_id']}}}

    def test_completed_profile_accepted(self):
        run.check_profile(PLAN, self.fixture())

    def test_pending_refused(self):
        value = self.fixture(); value['state'] = 'test_submitted'
        with self.assertRaisesRegex(ValueError, 'COMPLETED_PROFILE_REQUIRED'):
            run.check_profile(PLAN, value)

    def test_drift_refused(self):
        value = self.fixture(); value['result']['binding']['binding_id'] = 'other'
        with self.assertRaisesRegex(ValueError, 'PROFILE_SELECTION_CHANGED'):
            run.check_profile(PLAN, value)

    def test_extra_login_setup_refused(self):
        value = self.fixture(); value['login_start_operation'] = {'state': 'pending'}
        with self.assertRaisesRegex(ValueError, 'EXTRA_SETUP_EFFECT_NOT_SELECTED'):
            run.check_profile(PLAN, value)

    def test_exact_command_no_setup_or_chat(self):
        arguments = PLAN['nexus']['cli_arguments']
        self.assertIn('--no-chat', arguments)
        self.assertIn('--json', arguments)
        for flag in ('--approve', '--start', '--start-at-login', '--new-agent', '--remote-draft'):
            self.assertNotIn(flag, arguments)

    def test_connector_not_executable(self):
        self.assertIsNone(PLAN['connector']['canonical_argv'])
        self.assertFalse(PLAN['connector']['state_file_exists_observed'])


if __name__ == '__main__':
    unittest.main()
