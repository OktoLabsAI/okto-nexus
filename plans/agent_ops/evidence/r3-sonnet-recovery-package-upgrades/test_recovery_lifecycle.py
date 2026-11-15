"""Synthetic tests only: no product CLI, process, scheduler, network or service."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import copy
import json
import tempfile
import unittest

import recovery_context as context
import recovery_lifecycle as lifecycle
import recovery_connector as connector


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = {'revision': 2, 'executable': str(self.root / 'old/python.exe'),
                       'environment_prefix': str(self.root / 'old'), 'cwd': str(self.root),
                       'environment': {'PATH': 'synthetic'}, 'arguments': ['serve'],
                       'package_version': '0.3.3', 'core_version': '0.0.14', 'environment_fingerprint': 'old'}
        path = self.root / 'source.json'
        path.write_text(json.dumps(self.source))
        self.x = SimpleNamespace(python=str(self.root / 'new/python.exe'), PRIVATE=self.root,
             installed={'python_prefix': str(self.root / 'new')},
             C={'tasks': {'nexus': {'instance_id': 'own'}, 'connector': {'instance_id': 'own'}}},
             P={'source_contexts': {name: {'path': str(path), 'sha256': context.sha(path)}
                                    for name in ('nexus', 'connector')},
                'paths': {'server_home': str(self.root / 'server'), 'connector_state': str(self.root / 'connector')}})
        candidate = {'executable': self.x.python, 'environment_prefix': self.x.installed['python_prefix'],
                     'package': {'version': '0.3.3', 'digest': 'synthetic'},
                     'core': {'version': '0.0.14', 'digest': 'synthetic'}}
        target = dict(self.source, executable=candidate['executable'], environment_prefix=candidate['environment_prefix'],
                      environment_fingerprint='new')
        self.doc = {'plan_revision': 'a' * 64, 'plan': {'component': 'nexus', 'instance_id': 'own',
                    'source_context': self.source, 'target_context': target, 'candidate': candidate,
                    'source_receipt': None, 'source_generation': 'old-closed-generation', 'target_token': 'synthetic-private-only'}}

    def test_exact_upgrade_projection_excludes_private_token(self):
        value = lifecycle.validate_upgrade(self.x, 'nexus', self.doc)
        self.assertTrue(value['unchanged_execution_scope'])
        self.assertNotIn('target_token', json.dumps(value))
        self.assertNotIn('synthetic-private-only', json.dumps(value))

    def test_changed_execution_scope_refuses(self):
        for name, value in [('environment', {'PATH': 'changed'}), ('cwd', 'elsewhere'), ('arguments', ['changed'])]:
            with self.subTest(name=name):
                doc = copy.deepcopy(self.doc)
                doc['plan']['target_context'][name] = value
                with self.assertRaisesRegex(context.Refused, 'UPGRADE_CHANGED_EXECUTION_SCOPE'):
                    lifecycle.validate_upgrade(self.x, 'nexus', doc)

    def test_wrong_package_or_existing_installation_refuses(self):
        for change, code in [('package', 'UPGRADE_TARGET_NOT_PINNED_PACKAGE'), ('receipt', 'UPGRADE_EXPECTED_ABSENT_TASK')]:
            with self.subTest(change=change):
                doc = copy.deepcopy(self.doc)
                if change == 'package':
                    doc['plan']['candidate']['executable'] = str(self.root / 'other/python.exe')
                else:
                    doc['plan']['source_receipt'] = {'installed': True}
                with self.assertRaisesRegex(context.Refused, code):
                    lifecycle.validate_upgrade(self.x, 'nexus', doc)

    def test_explicit_upgrade_revision_and_noninteractive_connector(self):
        for component in ('nexus', 'connector'):
            argv = lifecycle.upgrade_argv(self.x, component, 'upgrade-apply', 'a' * 64)
            self.assertEqual(argv[-2:], ['--expected-revision', 'a' * 64])
            self.assertNotIn('--force', argv)
            with self.assertRaises(context.Refused):
                lifecycle.upgrade_argv(self.x, component, 'upgrade-apply')
        self.assertIn('--non-interactive', connector.commands(self.x)['install'])

    def test_filetime_only_canonical_positive_integer(self):
        self.assertEqual(connector.normalize_identity({'pid': 3, 'birth_token': 'filetime:42'}), {'pid': 3, 'birth': 42})
        for token in ('filetime:042', 'filetime:0', '42', None, 'filetime:４２'):
            with self.assertRaises(context.Refused):
                connector.normalize_identity({'pid': 3, 'birth_token': token})

    def test_new_namespace_tags_and_exclusive_atomic_receipts(self):
        x = SimpleNamespace(PUBLIC=self.root, plan_sha256='new-plan')
        context.public_save(x, 'new.json', {'value': 1})
        original = (self.root / 'new.json').read_bytes()
        self.assertFalse((self.root / 'new.json.writing').exists())
        with self.assertRaises(context.Refused):
            context.public_save(x, 'new.json', {'value': 2})
        self.assertEqual((self.root / 'new.json').read_bytes(), original)
        with self.assertRaises(context.Refused):
            context.require_tags({'phase1_plan_sha256': 'new-plan'}, x)

    def test_both_services_required_without_install_deadlock(self):
        x = context.RecoveryContext.__new__(context.RecoveryContext)
        with (patch('recovery_observation.current_ready', return_value={'host': 'nexus'}) as n,
              patch('recovery_connector.current_ready', return_value={'host': 'connector'}) as c):
            self.assertEqual(set(x.require_ready()), {'nexus', 'connector'})
            self.assertEqual(n.call_count, 1)
            self.assertEqual(c.call_count, 1)


if __name__ == '__main__':
    unittest.main()
