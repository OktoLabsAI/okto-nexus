from copy import deepcopy
from pathlib import Path
import hashlib
import sqlite3
import tempfile
import unittest
import history

class HistoryTests(unittest.TestCase):
    def test_real_readonly_sql_omits_payload_credentials_and_preserves_database(self):
        with tempfile.TemporaryDirectory() as root:
            p = Path(root) / 'fixture.db'
            with sqlite3.connect(p) as c:
                for table, columns in history.CORE.items():
                    c.execute('CREATE TABLE ' + table + '(' + ','.join(x + ' TEXT' for x in columns.split()) + ', secret_payload TEXT)')
                    names = columns.split()
                    c.execute('INSERT INTO ' + table + ' VALUES (' + ','.join('?' for _ in range(len(names) + 1)) + ')',
                              ['fixture-' + key for key in names] + ['SYNTHETIC_DO_NOT_EXPORT'])
            c.close()
            before = hashlib.sha256(p.read_bytes()).hexdigest()
            projected = history.projected_database(p, 'core')
            self.assertNotIn('SYNTHETIC_DO_NOT_EXPORT', str(projected))
            self.assertNotIn('secret_payload', str(projected))
            self.assertEqual(before, hashlib.sha256(p.read_bytes()).hexdigest())
            self.assertEqual(projected['tables']['session_claims']['count'], 1)

    def test_no_empty_success_when_schema_missing_or_rows_overflow(self):
        with tempfile.TemporaryDirectory() as root:
            p = Path(root) / 'fixture.db'
            sqlite3.connect(p).close()
            with self.assertRaises(sqlite3.OperationalError):
                history.projected_database(p, 'core')
            with sqlite3.connect(p) as c:
                for table, columns in history.CORE.items():
                    c.execute('CREATE TABLE ' + table + '(' + ','.join(x + ' TEXT' for x in columns.split()) + ')')
                c.executemany('INSERT INTO operations_v2(operation_id) VALUES(?)', [(str(i),) for i in range(history.MAX_ROWS + 1)])
            c.close()
            with self.assertRaisesRegex(RuntimeError, 'PROJECTION_ROW_BOUND_EXCEEDED'):
                history.projected_database(p, 'core')

    def test_change_in_authority_or_ownership_never_becomes_unchanged(self):
        base = {'databases': {'own.db': {'tables': {'facts': {'rows': [{
            'operation_id': 'old', 'used_executions': 2, 'expires_at': 'old-time', 'revoked': 1,
            'released': 0, 'reconciliation_pending': 1, 'next_sequence': 51}]}}}}}
        self.assertEqual(history.compare(base, deepcopy(base))['status'], 'HISTORY_UNCHANGED')
        for key, value in [('operation_id','new'), ('used_executions',0), ('expires_at','later'),
                           ('revoked',0), ('released',1), ('reconciliation_pending',0), ('next_sequence',52)]:
            changed = deepcopy(base)
            changed['databases']['own.db']['tables']['facts']['rows'][0][key] = value
            result = history.compare(base, changed)
            self.assertEqual(result['status'], 'CHANGES_REQUIRE_CANONICAL_RECONCILIATION')
            self.assertFalse(result['productive_replay_inferred_safe'])
            self.assertFalse(result['all_work_settled_inferred'])

    def test_new_or_missing_journal_is_not_a_clean_restart(self):
        before = {'databases': {'old.db': {'tables': {}}}}
        for after in [{'databases': {}}, {'databases': {'old.db': {'tables': {}}, 'new.db': {'tables': {}}}}]:
            result = history.compare(before, after)
            self.assertEqual(result['changes'][0]['change'], 'DATABASE_SET_CHANGED')
            self.assertFalse(result['active_operation_survival_claimed'])

if __name__ == '__main__':
    unittest.main()
