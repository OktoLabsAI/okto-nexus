"""Synthetic metadata refusal cases; no account POST/login or secret material."""
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
import json,sqlite3,sys,tempfile,time,unittest
HERE=Path(__file__).parent;sys.path.insert(0,str(HERE));import operator_recovery as r
class Tests(unittest.TestCase):
    def fixture(self,root):
        p=json.loads((HERE/'operator-recovery-plan.json').read_text());p['operator_profile_path']=str(root/'profile.json');p['auth_db']=str(root/'auth.db')
        (root/'profile.json').write_text(json.dumps(p['operator_metadata']))
        with closing(sqlite3.connect(p['auth_db'])) as c, c:
            c.executescript('CREATE TABLE account(id INTEGER,username TEXT);CREATE TABLE sessions(expires REAL);')
            c.execute('INSERT INTO account VALUES(1,?)',('m1-sonnet-human',))
        private=root/'paid-work/private';private.mkdir(parents=True)
        (private/'sonnet-budget.json').write_bytes((HERE/'budget-seed-approved.json').read_bytes())
        return p
    def test_active_session_refuses_and_zero_sessions_only_read(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=self.fixture(root)
            with patch.object(r,'HERE',root),patch('subprocess.Popen',side_effect=AssertionError('NO_CLI')):
                self.assertEqual(r.inspect(p)['active_sessions'],0)
                with closing(sqlite3.connect(p['auth_db'])) as c, c:c.execute('INSERT INTO sessions VALUES(?)',(time.time()+3600,))
                with self.assertRaisesRegex(RuntimeError,'ACTIVE_OPERATOR_SESSIONS'):r.inspect(p)
    def test_wrong_account_or_existing_work_reservation_refuses(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=self.fixture(root)
            with patch.object(r,'HERE',root):
                with closing(sqlite3.connect(p['auth_db'])) as c, c:c.execute('UPDATE account SET username=?',('not-campaign',))
                with self.assertRaisesRegex(RuntimeError,'DEDICATED_ACCOUNT_CHANGED'):r.inspect(p)
                with closing(sqlite3.connect(p['auth_db'])) as c, c:c.execute('UPDATE account SET username=?',('m1-sonnet-human',))
                (root/'paid-work/private'/(p['request_id']+'-reserved.json')).write_text('{}')
                with self.assertRaisesRegex(RuntimeError,'PAID_ADMISSION_ALREADY_RESERVED'):r.inspect(p)
if __name__=='__main__':unittest.main(verbosity=2)
