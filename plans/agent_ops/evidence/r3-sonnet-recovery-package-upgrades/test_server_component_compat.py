import copy
import unittest
from test_recovery_lifecycle import Tests as Fixture
import recovery_server_component_compat as compat
from recovery_context import Refused


class Tests(unittest.TestCase):
    def setUp(self):
        self.fixture = Fixture()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.document = copy.deepcopy(self.fixture.doc)
        self.document['plan']['component'] = 'server'

    def test_server_label_validates_without_rewriting_canonical_document(self):
        original = copy.deepcopy(self.document)
        result = compat.validate_server_plan(self.fixture.x, self.document)
        self.assertEqual(result['component'], 'server')
        self.assertEqual(result['campaign_component'], 'nexus')
        self.assertEqual(self.document, original)

    def test_other_component_refused(self):
        for value in ('nexus', 'connector', None):
            self.document['plan']['component'] = value
            with self.assertRaises(Refused):
                compat.validate_server_plan(self.fixture.x, self.document)

    def test_scope_guards_retained(self):
        self.document['plan']['target_context']['cwd'] = 'changed'
        with self.assertRaisesRegex(Refused, 'UPGRADE_CHANGED_EXECUTION_SCOPE'):
            compat.validate_server_plan(self.fixture.x, self.document)


if __name__ == '__main__':
    unittest.main()
