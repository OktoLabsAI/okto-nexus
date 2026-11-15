from pathlib import Path
from contextlib import closing
import copy
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import next_connect as candidate


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.plan = {'profile': 'm1-sonnet-remote-recovery02', 'agent_id': 'm1-sonnet-remote',
                     'server_id': 'server', 'workspace_id': 'workspace', 'origin': 'http://127.0.0.1:58631',
                     'paths': {'connector_state': str(root / 'state'), 'connector_project': str(root)}}
        self.scope = {'server_id': 'server', 'agent_id': 'm1-sonnet-remote', 'workspace_id': 'workspace',
                      'adapter_id': 'claude_stream', 'binding_id': 'binding'}
        self.completed = {'profile': self.plan['profile'], 'current_credential_epoch': 2,
                          'material_status': 'reuse_existing', 'remote_scope': self.scope}
        self.profile = {'state': 'done', 'result': {'saved': True}, 'remote_scope': self.scope}
        self.rotation = {'status': 'ROTATED_ONCE_IMPORTED_ONCE', 'current_epoch': 2,
                         'agent_id': 'm1-sonnet-remote', 'server_id': 'server'}
        self.dbpath = root / 'fixture.db'
        with closing(sqlite3.connect(self.dbpath)) as db, db:
            db.executescript('''CREATE TABLE execution_operations(server_id,executor_id,operation_id,subject_agent_id,workspace_id);
              CREATE TABLE execution_receipts(server_id,executor_id,operation_id,receipt_revision,stage);
              CREATE TABLE runtime_execution_grants(grant_id,revision,max_executions,used_executions,expires_at,revoked_at,represented_agent_id,workspace_id);''')
            db.execute('INSERT INTO runtime_execution_grants VALUES (?,?,?,?,?,?,?,?)',
                       ('grant', 1, 3, 0, 'future', None, 'm1-sonnet-remote', 'workspace'))

    def test_actual_installed_parser_has_no_productive_start_or_credential_input(self):
        from okto_nexus_connector.cli.main import build_parser
        argv = candidate.connect_args(self.plan)
        args = build_parser().parse_args(argv)
        self.assertFalse(args.start)
        self.assertFalse(args.credential_stdin)
        self.assertFalse(args.non_interactive)
        self.assertFalse(args.json)
        self.assertEqual(args.request_id, 'm1-sonnet-remote-setup-02')
        self.assertEqual(args.identity, 'm1-sonnet-remote')

    def test_done_and_epoch_two_are_both_required(self):
        self.assertEqual(candidate.validate_completed(self.plan, self.completed, self.profile, self.rotation), self.scope)
        for object_name, field, value in [('profile', 'state', 'awaiting_finish'),
                                          ('completed', 'current_credential_epoch', 1),
                                          ('rotation', 'status', 'UNCONFIRMED')]:
            values = {k: copy.deepcopy(getattr(self, k)) for k in ('completed', 'profile', 'rotation')}
            values[object_name][field] = value
            with self.assertRaises(candidate.require.__globals__['Refused']):
                candidate.validate_completed(self.plan, **values)

    def test_zero_admission_allowed_but_terminal_receipt_is_not_settlement(self):
        zero = candidate.accounting(self.dbpath, self.plan)
        self.assertEqual(zero['operation_count'], 0)
        with closing(sqlite3.connect(self.dbpath)) as db, db:
            db.execute('INSERT INTO execution_operations VALUES (?,?,?,?,?)', ('server', 'executor', 'op', 'm1-sonnet-remote', 'workspace'))
            db.execute('INSERT INTO execution_receipts VALUES (?,?,?,?,?)', ('server', 'executor', 'op', 1, 'SUCCEEDED'))
        with self.assertRaisesRegex(Exception, 'POST_PAID_SETTLEMENT_PROOF_REQUIRED'):
            candidate.accounting(self.dbpath, self.plan)

    def test_pending_or_unknown_work_refuses_before_stop(self):
        with closing(sqlite3.connect(self.dbpath)) as db, db:
            db.execute('INSERT INTO execution_operations VALUES (?,?,?,?,?)', ('server', 'executor', 'op', 'm1-sonnet-remote', 'workspace'))
        with self.assertRaisesRegex(Exception, 'POST_PAID_SETTLEMENT_PROOF_REQUIRED'):
            candidate.accounting(self.dbpath, self.plan)
        with closing(sqlite3.connect(self.dbpath)) as db, db:
            db.execute('INSERT INTO execution_receipts VALUES (?,?,?,?,?)', ('server', 'executor', 'op', 1, 'RUNNING'))
        with self.assertRaisesRegex(Exception, 'POST_PAID_SETTLEMENT_PROOF_REQUIRED'):
            candidate.accounting(self.dbpath, self.plan)

    def test_old_exits_never_prove_uncaptured_post_connect_cohort_exit(self):
        x = candidate.Context.__new__(candidate.Context)
        x.connect_selected = True
        x.post_connect_capture_complete = False
        closed, writes = [], []
        x.handles = [SimpleNamespace(exited=lambda: True, close=lambda: closed.append(True))]
        x.children = [SimpleNamespace(poll=lambda: 0)]
        x.save = lambda *args: writes.append(args)
        with patch('next_connect.time.monotonic', side_effect=[0, 1, 7201]), patch('next_connect.time.sleep') as sleep:
            x.handoff_and_close(RuntimeError('synthetic missing runtime capture'))
        sleep.assert_called_once_with(.5)
        self.assertEqual(len(closed), 1)
        self.assertFalse(writes[0][1]['cleanup_claimed'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
