"""Synthetic approval records stay in memory; no actual authorization is created."""
from copy import deepcopy
from pathlib import Path
import json,sys,unittest,tempfile
sys.path.insert(0,str(Path(__file__).resolve().parent))
from successor_policy import HERE,IDS,POLICY,history,authorize,convert,validate_history
from sonnet_usage import Ledger,Unknown,restore_budget,checkpoint_budget
from remote_work import effect_transport,reserve_before_dispatch

class Tests(unittest.TestCase):
    def setUp(self):
        self.source=json.loads((HERE/'historical-budget.json').read_bytes())
        self.candidate=json.loads((HERE/'candidate.json').read_bytes())
        self.approval={'explicit_user_approval':True,'user_response':'SYNTHETIC TEST ONLY',
            'response_reference':'fixture:not-real','proposal_sha256':self.candidate['proposal']['sha256'],
            'policy':POLICY,'carry_tokens':144004,'charged_requests':2,'new_requests_max':2}

    def converted(self):return convert(self.source,self.approval,self.candidate)

    def test_current_cap_rejects_before_reservation_or_effect(self):
        budget=history(self.source)
        self.assertEqual(budget.reservation_estimate('useful'),244846)
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'reserved.json'
            with self.assertRaisesRegex(Unknown,'HEADROOM'):reserve_before_dispatch(budget,'useful',IDS['useful'],path)
            self.assertFalse(path.exists())
        self.assertEqual((budget.known,budget.limit),(144004,200000))

    def test_pending_or_mismatched_approval_cannot_convert(self):
        for record in (None,{},dict(self.approval,explicit_user_approval=False),
                       dict(self.approval,proposal_sha256='wrong'),dict(self.approval,carry_tokens=0),
                       dict(self.approval,user_response='')):
            with self.subTest(record=record):
                with self.assertRaises(RuntimeError):convert(self.source,record,self.candidate)

    def test_approved_policy_keeps_exact_historical_rows_and_charge(self):
        derived=self.converted()
        self.assertEqual(derived['state']['sessions'],self.source['state']['sessions'])
        budget=restore_budget(derived)
        self.assertEqual((budget.known,budget.limit,budget.preventive,budget.max_requests),(144004,500000,480000,4))
        self.assertEqual(sum(len(x.reserved) for x in budget.sessions.values()),2)
        self.assertEqual(budget.check_admission('useful')['reserved_next'],244846)
        validate_history(budget,derived)

    def test_roundtrip_seal_and_history_tampering_refused(self):
        derived=self.converted();budget=restore_budget(json.loads(json.dumps(derived)))
        self.assertEqual(restore_budget(checkpoint_budget(budget)).known,144004)
        bad=deepcopy(self.source);bad['state']['sessions'][0]['known']+=1
        with self.assertRaisesRegex(Unknown,'CHECKPOINT_CHANGED'):history(bad)
        next(iter(budget.sessions.values())).reserved=['different-old-charge']
        with self.assertRaisesRegex(RuntimeError,'HISTORICAL_USAGE'):validate_history(budget,derived)

    def test_replay_and_total_four_admissions_fenced(self):
        seed=self.converted();budget=restore_budget(seed)
        scope=dict(next(iter(budget.sessions.values())).scope,session_id='synthetic-new',stream_epoch='synthetic-new')
        new=Ledger(scope,limit=budget.limit,preventive=budget.preventive,max_requests=budget.max_requests)
        budget.attach(new)
        old=next(iter(budget.sessions.values())).reserved[0]
        with self.assertRaisesRegex(Unknown,'REPLAY'):budget.reserve(new,old)
        budget.reserve(new,IDS['useful']);new.active=None;new.terminal_coverage=True
        budget.reserve(new,IDS['continuation'],phase='continuation');new.active=None;new.terminal_coverage=True
        validate_history(budget,seed)
        with self.assertRaisesRegex(Unknown,'ALLOCATION'):budget.check_admission('continuation')
        self.assertEqual(sum(len(x.reserved) for x in budget.sessions.values()),4)

    def test_continuation_rechecks_actual_headroom_and_effect_threshold(self):
        budget=restore_budget(self.converted())
        scope=dict(next(iter(budget.sessions.values())).scope,session_id='new',stream_epoch='new')
        new=Ledger(scope,limit=500000,preventive=480000,max_requests=4);budget.attach(new)
        new.known=100000
        with self.assertRaisesRegex(Unknown,'HEADROOM'):budget.check_admission('continuation')
        calls=[];state={'budget':budget,'monitor':None,'started':0,'containment':False}
        wrapped=effect_transport(lambda *args:calls.append(args),state,clock=lambda:1)
        wrapped('POST','synthetic',{})
        new.known=480000-144004
        with self.assertRaisesRegex(Unknown,'EFFECT_ADMISSION_CLOSED'):wrapped('POST','synthetic',{})
        self.assertEqual(len(calls),1)

if __name__=='__main__':unittest.main(verbosity=2)
