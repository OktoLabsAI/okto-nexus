import copy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('cleanup', Path(__file__).with_name('cleanup.py'))
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)

class Tests(unittest.TestCase):
    def resolution(self):
        return dict(scope=c.SCOPE, client_intent_id=c.REQUEST_ID, session_id=c.SESSION,
          semantic_intent={'action':'turn.interrupt', 'target':c.REQUEST['target']},
          can_submit=True, blockers=[], operation_id='op_cleanup', resolution_revision='rev', intent_hash='hash')
    def run_case(self, value, failure=None):
        calls, saved = [], {}
        def http(method, path, body):
            calls.append((method,path,body))
            if len(calls)==1:
                return value
            if failure:
                raise TimeoutError()
            return dict(scope=c.SCOPE, operation_id='op_cleanup', intent_hash='hash', action='turn.interrupt')
        def save(name, item):
            self.assertNotIn(name,saved)
            saved[name]=item
        return calls,saved,lambda:c.contain(http,save)
    def test_exact_one_containment_and_no_productive_action(self):
        calls,saved,run=self.run_case(self.resolution());run()
        self.assertEqual(len(calls),2)
        self.assertEqual(calls[0][2],c.REQUEST)
        self.assertEqual(set(calls[1][2]),{'client_intent_id','operation_id','resolution_revision','intent_hash'})
        self.assertEqual(set(saved),{'resolve-reserved','resolved','admit-reserved','admitted'})
    def test_wrong_target_never_admitted(self):
        value=copy.deepcopy(self.resolution());value['semantic_intent']['target']['expected_turn_id']='other'
        calls,_,run=self.run_case(value)
        with self.assertRaisesRegex(RuntimeError,'RESOLUTION_MISMATCH'):run()
        self.assertEqual(len(calls),1)
    def test_wrong_scope_never_admitted(self):
        value=copy.deepcopy(self.resolution());value['scope']['authorization_revision']=3
        calls,_,run=self.run_case(value)
        with self.assertRaisesRegex(RuntimeError,'EXACT_SCOPE_CHANGED'):run()
        self.assertEqual(len(calls),1)
    def test_blocked_never_admitted(self):
        value=self.resolution();value['can_submit']=False;value['blockers']=['STALE_TURN']
        calls,_,run=self.run_case(value)
        with self.assertRaisesRegex(RuntimeError,'CONTAINMENT_BLOCKED'):run()
        self.assertEqual(len(calls),1)
    def test_unknown_post_never_retried(self):
        calls,saved,run=self.run_case(self.resolution(),True)
        with self.assertRaises(TimeoutError):run()
        self.assertEqual(len(calls),2)
        self.assertIn('admit-reserved',saved)
        self.assertNotIn('admitted',saved)

if __name__=='__main__':unittest.main()
