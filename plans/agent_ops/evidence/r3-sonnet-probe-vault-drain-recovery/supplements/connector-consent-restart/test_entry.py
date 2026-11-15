import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

spec = importlib.util.spec_from_file_location('consent_restart_entry', Path(__file__).with_name('entry.py'))
entry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entry)


class Guards(unittest.TestCase):
    def test_consent_epoch_and_fresh_cohort(self):
        state = SimpleNamespace(preferences={'vault.fallback_file.approved': True},
            identity_for=lambda *args: SimpleNamespace(credential_epoch=2, revoked=False))
        entry.validate_identity(state, 'server', 'agent')
        state.preferences['vault.fallback_file.approved'] = False
        with self.assertRaises(entry.require.__globals__['Refused']):
            entry.validate_identity(state, 'server', 'agent')
        old = {'generation': 'old', 'cohort': {'cycle_id': 'old'}, 'instance_id': 'same',
               'task': {'digest': 'same', 'name': 'same'}}
        new = dict(old, generation='new', cohort={'cycle_id': 'new'})
        entry.validate_fresh(new, old)
        with self.assertRaises(entry.require.__globals__['Refused']):
            entry.validate_fresh(dict(new, cohort=old['cohort']), old)

    def test_routing_preserves_nexus_and_existing_other_views(self):
        original = entry.ORIGINAL_CURRENT_READY
        original_method = entry.RecoveryContext.require_ready
        original_connector = entry.connector.current_ready
        seen = []
        entry.ORIGINAL_CURRENT_READY = lambda context: seen.append(context.PUBLIC) or 'connector'
        try:
            entry.install_routing('selected-plan')
            base = SimpleNamespace(PUBLIC=entry.RECOVERY / 'public', require_nexus_ready=lambda: 'nexus')
            self.assertEqual(entry.RecoveryContext.require_ready(base), {'nexus': 'nexus', 'connector': 'connector'})
            self.assertEqual(seen[-1], entry.HERE / 'public')
            other = SimpleNamespace(PUBLIC=entry.RECOVERY / 'post-svc20/public')
            entry.connector.current_ready(other)
            self.assertEqual(seen[-1], other.PUBLIC)
            self.assertEqual(base.PUBLIC, entry.RECOVERY / 'public')
        finally:
            entry.ORIGINAL_CURRENT_READY = original
            entry.RecoveryContext.require_ready = original_method
            entry.connector.current_ready = original_connector


if __name__ == '__main__':
    unittest.main()
