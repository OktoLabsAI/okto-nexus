import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('force_once', Path(__file__).with_name('force_once.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ForceGates(unittest.TestCase):
    def test_explicit_scope_authorization_required(self):
        proposal = {'target': {'owner': {'pid': 36068}}}
        value = {'status': 'SPECIFIC_CONNECTOR_FORCE_AUTHORIZED', 'proposal_sha256': 'p',
                 'max_canonical_force_calls': 1, 'force_authorized': True,
                 'target': proposal['target'], 'user_message_reference': 'explicit test fixture'}
        module.validate_authorization(value, proposal, 'p')
        for changed in ({'force_authorized': False}, {'max_canonical_force_calls': 2}, {'proposal_sha256': 'old'}):
            with self.assertRaises(RuntimeError):
                module.validate_authorization(dict(value, **changed), proposal, 'p')

    def test_force_available_is_not_implied_by_stopping(self):
        selected = {'pid': 36068, 'generation': 'exact', 'instance_id': 'exact'}
        raw = dict(selected, running=True, ipc_ok=True, draining=True, state='stopping',
                   drain={'state': 'DRAINING_PENDING', 'force_available': True, 'force_requested': False})
        module.validate_status(raw, selected)
        with self.assertRaises(RuntimeError):
            module.validate_status(dict(raw, generation='changed'), selected)
        with self.assertRaises(RuntimeError):
            module.validate_status(dict(raw, drain=dict(raw['drain'], force_available=False)), selected)


if __name__ == '__main__':
    unittest.main()
