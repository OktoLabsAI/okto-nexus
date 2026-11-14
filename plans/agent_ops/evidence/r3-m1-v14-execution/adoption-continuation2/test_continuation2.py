import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('entry', HERE / 'continue_adoption2.py')
entry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entry)

def require(ok, code):
    if not ok:
        raise RuntimeError(code)

class ContinuationTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((HERE / 'manifest.json').read_bytes())
        self.previous = sys.modules.get('driver_common')
        self.tags = []
        sys.modules['driver_common'] = SimpleNamespace(require_tags=lambda value, ctx: self.tags.append(value))
        self.helper = SimpleNamespace(require=require, read=lambda path: json.loads(Path(path).read_bytes()))

    def tearDown(self):
        if self.previous is None:
            sys.modules.pop('driver_common', None)
        else:
            sys.modules['driver_common'] = self.previous

    def test_exact_prior_failure_passes_without_effects(self):
        entry.validate_prior(self.helper, object(), self.manifest)
        self.assertEqual(len(self.tags), 2)

    def test_tampered_prior_receipt_rejected(self):
        self.manifest['prior_continuation']['pins']['failure']['sha256'] = '0' * 64
        with self.assertRaisesRegex(RuntimeError, 'PRIOR_CONTINUATION_CHANGED'):
            entry.validate_prior(self.helper, object(), self.manifest)

    def test_advanced_controller_rejected_even_with_matching_pin(self):
        with tempfile.TemporaryDirectory() as directory:
            pin = self.manifest['prior_continuation']['pins']['failure']
            value = json.loads(Path(pin['path']).read_bytes())
            value['controller_exists'] = True
            path = Path(directory) / 'failure.json'
            path.write_text(json.dumps(value), encoding='utf-8')
            pin.update(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            with self.assertRaisesRegex(RuntimeError, 'PRIOR_NOT_GET_ONLY_PRE_CONTROLLER_FAILURE'):
                entry.validate_prior(self.helper, object(), self.manifest)

if __name__ == '__main__':
    unittest.main()
