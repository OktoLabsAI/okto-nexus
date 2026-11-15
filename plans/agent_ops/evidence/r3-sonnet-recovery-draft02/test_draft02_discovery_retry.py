import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from draft02_discovery_retry import NativePathEnvironment, discovery_proxy, require_draft_unselected, prior_discovery
from recovery_context import reserve, sha, Refused
from recovery_onboarding import Context


class Tests(unittest.TestCase):
    def test_only_pinned_native_parent_is_added_to_owned_path(self):
        env = {'PATH': os.pathsep.join(['C:/Windows/System32', 'C:/Program Files/Git/cmd']), 'SAFE': 'kept'}
        base = SimpleNamespace(connector_env=lambda: dict(env))
        selected = {'path': 'C:/Users/jpamb/.local/bin/claude.exe'}
        actual = NativePathEnvironment(base, selected).connector_env()
        self.assertEqual(actual['PATH'].split(os.pathsep), [str(Path(selected['path']).resolve().parent), *env['PATH'].split(os.pathsep)])
        self.assertEqual(actual['SAFE'], 'kept')
        self.assertEqual(base.connector_env(), env)

    def test_retry_invoke_preserves_original_files_and_passes_exact_environment(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp);private = root / 'private';public = root / 'public'
            private.mkdir();public.mkdir()
            original = private / 'draft02-discover.stdout';original.write_text('original-empty-inventory')
            X = SimpleNamespace(PRIVATE=private, PUBLIC=public, ROOT=root, plan_sha='plan')
            X.base = NativePathEnvironment(SimpleNamespace(connector_env=lambda: {'PATH': 'C:/Windows/System32'}), {'path': 'C:/Users/jpamb/.local/bin/claude.exe'})
            X.save = lambda name, value: reserve(public / name, dict(value, draft_plan_sha256='plan'))
            before = original.read_bytes();calls = []

            def launch(argv, **kwargs):
                calls.append((argv, kwargs['env']))
                kwargs['stdout'].write(json.dumps({'candidates': [{'fixture': True}]}).encode())
                return SimpleNamespace(returncode=0, communicate=lambda data: None)

            with patch('recovery_onboarding.subprocess.Popen', side_effect=launch):
                result = Context.invoke(discovery_proxy(X), 'discover', ['synthetic-discover'])
            self.assertEqual(original.read_bytes(), before)
            self.assertEqual(result, prior_discovery(X))
            self.assertTrue((public / 'draft02-discover-retry1-reserved.json').is_file())
            self.assertFalse((public / 'draft02-discover-reserved.json').exists())
            self.assertEqual(calls[0][1], X.base.connector_env())
            self.assertTrue(sha(original))

    def test_original_draft_reservation_prevents_any_continuation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            X = SimpleNamespace(PUBLIC=root, draft_path=root / 'draft.json')
            require_draft_unselected(X)
            (root / 'draft02-draft-reserved.json').write_text('{}')
            with self.assertRaisesRegex(Refused, 'ORIGINAL_DRAFT_ALREADY_SELECTED'):
                require_draft_unselected(X)


if __name__ == '__main__':
    unittest.main(verbosity=2)
