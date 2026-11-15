from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import json
import tempfile
import unittest
from unittest.mock import patch

from recovery_binding import Context, canonical_commands, validate_review, validate_done, run
from recovery_context import sha, read_json, Refused

HERE = Path(__file__).resolve().parent


class Tests(unittest.TestCase):
    def setUp(self):
        self.p = read_json(HERE / 'binding02-plan.json')
        self.draft = read_json(self.p['draft']['path'])

    def document(self):
        p = self.p
        review = {'draft': self.draft, 'review_revision': 'a' * 64, 'selection': {
            'server_id': p['server_id'], 'identity': {'mode': 'select', 'agent_id': p['agent_id']},
            'workspace': {'mode': 'select', 'workspace_id': p['workspace_id']},
            'credential': {'mode': 'reuse_existing', 'expected_epoch': 2}}}
        return {'kind': 'remote_project_setup', 'state': 'awaiting_finish', 'server_id': p['server_id'],
            'review_revision': 'a' * 64, 'remote_review': review,
            'selection': {'operator_profile': p['operator_profile'], 'create_agent': False, 'agent': p['agent_id']},
            'bootstrap': {k: p[k] for k in ('server_id', 'agent_id', 'workspace_id')} |
                {'setup_run_id': p['setup_request_id'], 'credential_epoch': 2},
            'material_status': 'reuse_existing'}

    def test_actual_package_context_and_host_parser_never_request_credential(self):
        from okto_nexus_connector.cli.main import build_parser
        with patch('subprocess.Popen', side_effect=AssertionError('unexpected process')):
            X = Context(HERE / 'binding02-plan.json', sha(HERE / 'binding02-plan.json'))
        _, review, host = canonical_commands(X)
        parsed = build_parser().parse_args(host[host.index('-m') + 2:])
        self.assertEqual(parsed.identity, self.p['agent_id'])
        self.assertFalse(parsed.credential_stdin)
        self.assertIsNone(parsed.credential_env)
        self.assertIsNone(parsed.mcp_entry)
        self.assertNotIn('--new-agent', review)
        self.assertIn('--workspace-id', review)

    def test_review_requires_existing_epoch_two_identity_and_exact_draft(self):
        doc = self.document()
        validate_review(doc, self.p, self.draft)
        for key, value in [('credential', {'mode': 'issue_once', 'expected_epoch': 0}),
                           ('identity', {'mode': 'create', 'agent_id': self.p['agent_id']}),
                           ('workspace', {'mode': 'create', 'workspace_id': None})]:
            changed = deepcopy(doc)
            changed['remote_review']['selection'][key] = value
            with self.assertRaises(Refused):
                validate_review(changed, self.p, self.draft)

    def test_actual_installed_complete_requires_binding_get_and_correlated_finish(self):
        from okto_nexus.application.remote_terminal_setup import RemoteProjectSetup
        p = self.p
        binding = {k: p[k] for k in ('server_id', 'agent_id', 'workspace_id')}
        binding.update(state='APPROVED', executor_id='executor', binding_id='binding', workspace_binding_id='workspace-binding',
                       adapter_id='claude_stream', candidate_ref=self.draft['installation']['candidate_ref'])
        doc = self.document()
        doc['final_binding'] = {k: binding[k] for k in ('server_id', 'agent_id', 'workspace_id', 'executor_id', 'binding_id')}
        doc['final_binding'].update(proposal_id='proposal', finish_id='proposal_setup')
        calls, saves = [], []

        def call(method, path, body=None):
            calls.append((method, path))
            return binding

        RemoteProjectSetup(call, saves.append, origin='http://127.0.0.1:58631')._complete(doc)
        self.assertEqual(calls, [('GET', '/api/v1/runtime-management/connections/bindings/binding')])
        self.assertEqual(validate_done(doc, p, self.draft), doc['remote_scope'])
        changed = deepcopy(doc);changed['final_binding']['finish_id'] = 'unrelated'
        with self.assertRaises(Refused):
            validate_done(changed, p, self.draft)
        self.assertEqual(len(saves), 1)

    def host_finish(self, stage):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'profile.json'
            doc = self.document();path.write_text(json.dumps(doc))
            local = {'stage': stage, 'result': {'saved': stage == 'done'}}
            calls, evidence = [], []
            X = SimpleNamespace(P=self.p, base=SimpleNamespace(python='synthetic-python'), profile_path=path,
                handoff_path=Path(temp) / 'handoff.json', rotation=lambda: {'sha256': 'rotation'},
                retained_review=lambda: (doc, {}), require_prior=lambda action: evidence.append(action),
                local_setup=lambda: local, save=lambda name, value: evidence.append((name, value)))

            def invoke(action, argv, **kwargs):
                calls.append(action);local.update(stage='done', result={'saved': True})

            X.invoke = invoke
            run(X, 'host-finish')
            self.assertEqual(evidence[0], 'operator-decide')
            self.assertTrue(evidence[-1][0].endswith('host-finish-result.json'))
            return calls

    def test_host_finish_resumes_exact_pending_host_instead_of_assuming_background(self):
        self.assertEqual(self.host_finish('apply'), ['host-finish'])

    def test_host_finish_can_observe_actual_already_done_checkpoint(self):
        self.assertEqual(self.host_finish('done'), [])

    def test_host_inventory_pending_rc_zero_is_not_completion_or_automatic_retry(self):
        with tempfile.TemporaryDirectory() as temp:
            doc = self.document();doc['state'] = 'awaiting_host'
            local, calls = [None], []
            X = SimpleNamespace(P=self.p, base=SimpleNamespace(python='synthetic-python'),
                handoff_path=Path(temp) / 'handoff.json', rotation=lambda: {},
                retained_review=lambda: (doc, {}), require_prior=lambda action: None,
                local_setup=lambda: local[0], save=lambda *a: self.fail('unconfirmed stage published as success'))

            def invoke(action, argv, **kwargs):
                calls.append(action)
                local[0] = {'stage': 'realize', 'remote_setup': {'setup_run_id': self.p['setup_request_id'], 'review_revision': doc['review_revision']}}

            X.invoke = invoke
            with self.assertRaisesRegex(Refused, 'HOST_PREPARATION_UNCONFIRMED'):
                run(X, 'host-prepare')
            self.assertEqual(calls, ['host-prepare'])
            self.assertEqual(local[0]['stage'], 'realize')

    def test_operator_boundary_can_return_actual_configured_without_extra_decision(self):
        with tempfile.TemporaryDirectory() as temp:
            doc = self.document();doc['state'] = 'awaiting_host'
            path = Path(temp) / 'profile.json';path.write_text(json.dumps(doc))
            calls, saved = [], []
            X = SimpleNamespace(P=self.p, base=SimpleNamespace(python='synthetic-python'), profile_path=path,
                handoff_path=Path(temp) / 'handoff.json', rotation=lambda: {},
                retained_review=lambda: (doc, {}), require_prior=lambda action: None,
                save=lambda name, value: saved.append(value))

            def invoke(action, argv, **kwargs):
                calls.append(action)
                doc['state'] = 'done';path.write_text(json.dumps(doc))
                return {'state': 'configured'}

            X.invoke = invoke
            run(X, 'operator-decide')
            self.assertEqual(calls, ['operator-decide'])
            self.assertEqual(saved[0]['profile_state'], 'done')


if __name__ == '__main__':
    unittest.main(verbosity=2)
