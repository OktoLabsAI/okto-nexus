"""Offline guard qualification; subprocess and service observers are replaced."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path('C:/Users/jpamb/AppData/Local/Temp/m1-v12-bundle-bldo9qy7/successor14/work-request12')
sys.path.insert(0, str(ROOT))
import upgrade_environment as U
from okto_nexus.adapters.outbound.service_manager.context import document_revision

class UpgradeGuards(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='m1-upgrade-offline-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.private = self.root / 'private'; self.private.mkdir()
        source = {'revision': 1, 'executable': 'C:/old/python.exe', 'environment_prefix': 'C:/old',
                  'arguments': ['--port', '58631'], 'environment': {'PATH': 'C:/safe'}, 'cwd': 'C:/work'}
        candidate = {'executable': 'C:/new/python.exe', 'environment_prefix': 'C:/new',
                     'package': {'version': '0.3.3'}, 'core': {'version': '0.0.14'}}
        target = {**source, 'revision': 2, 'executable': candidate['executable'],
                  'environment_prefix': candidate['environment_prefix'], 'package_version': '0.3.3',
                  'core_version': '0.0.14', 'environment_fingerprint': document_revision(candidate)}
        self.body = {'component': 'server', 'instance_id': 'owned-instance', 'source_generation': 'old-generation',
                     'source_receipt': None, 'source_claim': None, 'source_context': source,
                     'target_context': target, 'candidate': candidate, 'target_token': 'PRIVATE_SENTINEL'}
        self.source_path = self.root / 'service-context.json'
        self.source_path.write_text(json.dumps(source), encoding='utf-8')
        self.snapshot = self.root / 'source-snapshot.json'
        self.snapshot.write_bytes(self.source_path.read_bytes())
        migration = {'generation': 'old-generation', 'source_context': self.pin(self.source_path),
                     'source_document_revision': document_revision(source),
                     'source_context_revision': document_revision(source), 'source_snapshot': self.pin(self.snapshot)}
        for key in ('run', 'shutdown'):
            p = self.root / (key + '.json'); p.write_text('{}', encoding='utf-8'); migration[key] = self.pin(p)
        self.context = SimpleNamespace(C={'tasks': {'nexus': {'instance_id': 'owned-instance', 'name': 'owned-task'}},
                'service_selection_args': ['--home', str(self.root)]}, amendment={'migration': migration},
                installed={'python': candidate['executable'], 'python_prefix': candidate['environment_prefix']},
                PRIVATE=self.private, ROOT=self.root, env=lambda: {})

    @staticmethod
    def pin(path): return {'path': str(path), 'sha256': U.sha(path)}

    def document(self, body=None):
        body = copy.deepcopy(self.body if body is None else body)
        return {'plan': body, 'plan_revision': document_revision(body)}

    def rejects(self, body):
        with self.assertRaises((RuntimeError, ValueError, KeyError)):
            U.validate_plan(self.context, self.document(body))

    def test_valid_environment_only_plan(self):
        value = self.document()
        self.assertEqual(U.validate_plan(self.context, value), value['plan_revision'])

    def test_revision_tampering(self):
        value = self.document(); value['plan']['target_token'] = 'changed'
        with self.assertRaises(RuntimeError): U.validate_plan(self.context, value)

    def test_other_generation(self):
        body = copy.deepcopy(self.body); body['source_generation'] = 'new-owner'; self.rejects(body)

    def test_other_environment(self):
        body = copy.deepcopy(self.body); body['candidate']['executable'] = body['target_context']['executable'] = 'C:/foreign/python.exe'
        self.rejects(body)

    def test_non_environment_setting_change(self):
        body = copy.deepcopy(self.body); body['target_context']['arguments'] = ['--port', '1']; self.rejects(body)

    def test_changed_source_and_target_cannot_create_new_authority(self):
        body = copy.deepcopy(self.body)
        body['source_context']['environment'] = {'PATH': 'C:/foreign'}
        body['target_context']['environment'] = {'PATH': 'C:/foreign'}
        self.rejects(body)

    def test_installed_native_source_not_in_scope(self):
        body = copy.deepcopy(self.body); body['source_receipt'] = {'token': 'unexpected'}; self.rejects(body)

    def test_changed_drain_evidence_prevents_process(self):
        Path(self.context.amendment['migration']['run']['path']).write_text('{"changed":true}', encoding='utf-8')
        with patch.object(U, 'absent'), patch.object(U.subprocess, 'Popen') as spawn:
            with self.assertRaises(RuntimeError): U.execute(self.context, 'plan')
            spawn.assert_not_called()

    def test_apply_requires_exact_technical_review(self):
        path = self.private / 'environment-upgrade-plan.json'; path.write_text(json.dumps(self.document()), encoding='utf-8')
        with patch.object(U, 'absent'), patch.object(U.subprocess, 'Popen') as spawn:
            with self.assertRaises(FileNotFoundError): U.execute(self.context, 'apply')
            spawn.assert_not_called()

    def test_one_plan_invocation_keeps_private_plan_out_of_public_output(self):
        records = {}
        def save(context, name, value):
            if name in records: raise FileExistsError(name)
            records[name] = copy.deepcopy(value)
        def spawn(argv, **kwargs):
            self.assertNotIn('start', argv)
            self.assertNotIn('--force', argv)
            self.assertEqual(argv[argv.index('service') + 1], 'upgrade-plan')
            document = self.document()
            Path(argv[argv.index('--output') + 1]).write_text(json.dumps(document), encoding='utf-8')
            kwargs['stdout'].write(json.dumps(document).encode()); kwargs['stdout'].flush()
            return SimpleNamespace(wait=lambda: 0)
        with patch.object(U, 'absent'), patch.object(U, 'public_save', side_effect=save), patch.object(U.subprocess, 'Popen', side_effect=spawn) as process:
            self.assertEqual(U.execute(self.context, 'plan'), 0)
            with self.assertRaises(FileExistsError): U.execute(self.context, 'plan')
            self.assertEqual(process.call_count, 1)
        self.assertNotIn('PRIVATE_SENTINEL', json.dumps(records))
        self.assertTrue(records['environment-upgrade-plan-result.json']['plan_revision'])

if __name__ == '__main__': unittest.main(verbosity=2)
