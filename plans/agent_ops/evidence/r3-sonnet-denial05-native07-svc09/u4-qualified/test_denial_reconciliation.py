from pathlib import Path
from copy import deepcopy
import hashlib,json,sys,tempfile,unittest
from unittest.mock import patch
H=Path(__file__).parent;sys.path.insert(0,str(H))
import denial_reconciliation as d
from sonnet_usage import restore_budget
def read(p):return json.loads(Path(p).read_bytes())
def ref(p):return {'path':str(p),'sha256':hashlib.sha256(Path(p).read_bytes()).hexdigest()}
class Tests(unittest.TestCase):
    def setUp(self):
        self.selection=read(H/'root-counter-selection.json');p=read(self.selection['selected_proposal']['path']);e=p['evidence']
        self.args=[read(e[k]['path']) for k in ('diagnosis','reserved_attempt','admission','six_physical_exit')]
        self.args.append({c:read(x['path']) for c,x in self.selection['predecessor_selections'].items()})
        self.plan={'counter_selection':ref(H/'root-counter-selection.json'),'typed_denial05':ref(H/'typed-denial05.json'),'server_admission_history':ref(H/'server-admission-history.json'),'budget_seed':ref(H/'budget-seed-approved.json')}
        self.budget=restore_budget(read(H/'budget-seed-approved.json'))
    def test_actual_typed_denial_keeps_native_seed_and_all_server_history(self):
        self.assertEqual(d.validate_receipt(self.plan)['facts']['request_id'],d.DENIED)
        self.assertEqual((self.budget.known,self.budget.max_requests),(144004,4))
        self.assertEqual(self.budget.reservation_estimate('useful'),244846)
        self.assertEqual(sum(len(x.reserved) for x in self.budget.sessions.values()),2)
        with tempfile.TemporaryDirectory() as path:self.assertEqual(d.counts(path)['server_admissions'],3)
    def test_missing_or_uncertain_core_stream_dispatch_facts_refuse(self):
        cases=[('core_operations',[{'operation_id':d.OPEN}]),('core_launches',[{}]),('core_events',1),('receipts',[{}]),('event_count',1)]
        for key,value in cases:
            args=deepcopy(self.args);args[0][key]=value
            with self.subTest(key=key),self.assertRaises(RuntimeError):d.validate_evidence(*args)
        args=deepcopy(self.args);args[0]['dispatch'][0]['error']['possible_effect']=True
        with self.assertRaises(RuntimeError):d.validate_evidence(*args)
        args=deepcopy(self.args);args[0]['session'][0]['stream_epoch']='uncertain-stream'
        with self.assertRaises(RuntimeError):d.validate_evidence(*args)
    def test_scope_birth_and_other_denial_never_get_exception(self):
        for mutate in (lambda a:a[1].update(request_id=d.IDS['useful']),lambda a:a[2].update(session_id='other'),
                       lambda a:a[3]['exits']['connector']['child'].update(birth=1)):
            args=deepcopy(self.args);mutate(args)
            with self.assertRaises(RuntimeError):d.validate_evidence(*args)
    def test_pin_mismatch_or_policy_change_refuses(self):
        plan=deepcopy(self.plan);plan['typed_denial05']['sha256']='0'*64
        with self.assertRaises(RuntimeError):d.validate_receipt(plan)
        selection=deepcopy(self.selection);selection['policy']['native_max']=5
        with self.assertRaises(RuntimeError):d.selected_proof(selection)
    def test_denial_must_belong_to_original_paid_plan_and_its_cohorts(self):
        selection=deepcopy(self.selection);selection['denied_paid_plan']['sha256']='0'*64
        with self.assertRaises(RuntimeError):d.selected_proof(selection)
        selection=deepcopy(self.selection)
        selection['predecessor_selections']['nexus']=selection['predecessor_selections']['connector']
        with self.assertRaisesRegex(RuntimeError,'DENIAL_PREDECESSOR_SELECTION_CHANGED'):d.selected_proof(selection)
    def test_original_namespace_and_watcher_provenance_are_checked(self):
        original=d.read_json
        def changed_namespace(path):
            value=original(path)
            if str(path)==self.selection['selected_proposal']['path']:
                value=deepcopy(value);value['evidence']['reserved_attempt']['path']='C:/other/reserved.json'
            return value
        with patch.object(d,'read_json',side_effect=changed_namespace),self.assertRaisesRegex(RuntimeError,'DENIAL_EVIDENCE_NAMESPACE_CHANGED'):
            d.selected_proof(self.selection)
        def changed_watch(path):
            value=original(path)
            if str(path).endswith('nexus-exit-watch-started.json'):
                value=deepcopy(value);value['lifecycle_plan_sha256']='0'*64
            return value
        with patch.object(d,'read_json',side_effect=changed_watch),self.assertRaisesRegex(RuntimeError,'DENIAL_ORIGINAL_WATCH_COHORT_CHANGED'):
            d.selected_proof(self.selection)
    def test_unforwarded_or_unknown_new_attempt_stays_charged_and_replay_refuses(self):
        with tempfile.TemporaryDirectory() as path:
            with self.assertRaises(RuntimeError):d.reserve_attempt(self.plan,path,d.DENIED,self.budget)
            d.reserve_attempt(self.plan,path,d.IDS['useful'],self.budget)
            self.assertEqual((d.counts(path)['server_admissions'],d.counts(path)['native_forwarded_or_uncertain']),(4,3))
            # No Core ledger or result was created. This still counts as Native uncertain.
            with self.assertRaises(RuntimeError):d.reserve_attempt(self.plan,path,d.IDS['useful'],self.budget)
            d.reserve_attempt(self.plan,path,d.IDS['continuation'],self.budget)
            self.assertEqual((d.counts(path)['server_admissions'],d.counts(path)['native_forwarded_or_uncertain']),(5,4))
            with self.assertRaises(RuntimeError):d.reserve_attempt(self.plan,path,'new09',self.budget)
    def test_continuation_first_or_tampered_counter_refuses(self):
        with tempfile.TemporaryDirectory() as path:
            with self.assertRaises(RuntimeError):d.reserve_attempt(self.plan,path,d.IDS['continuation'],self.budget)
            d.reserve_attempt(self.plan,path,d.IDS['useful'],self.budget)
            f=next(Path(path).glob('server-attempt-*.json'));v=read(f);v['native_charge_upper_bound']=0;f.write_text(json.dumps(v))
            with self.assertRaises(RuntimeError):d.counts(path)
if __name__=='__main__':unittest.main(verbosity=2)
