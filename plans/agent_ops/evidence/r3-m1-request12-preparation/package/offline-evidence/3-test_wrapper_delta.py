import ast
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys,unittest
from types import SimpleNamespace

W=Path('C:/Users/jpamb/AppData/Local/Temp/m1-v12-bundle-bldo9qy7/successor14/work-request12')
CANDIDATE=Path(__file__).resolve().parent
sys.path.insert(0,str(CANDIDATE))
import test_successor as fixtures
sys.path.insert(0,str(W))
spec=importlib.util.spec_from_file_location('close_under_test',W/'close_campaign.py')
close=importlib.util.module_from_spec(spec);spec.loader.exec_module(close)

def require(ok,code):
    if not ok:raise RuntimeError(code)
tree=ast.parse((W/'local_work.py').read_text(encoding='utf-8'))
functions=ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('select_request','require_failed_predecessor','stop_attempt_projection')],type_ignores=[])
namespace={'require':require};exec(compile(functions,str(W/'local_work.py'),'exec'),namespace)

class Tests(unittest.TestCase):
    def test_real_wrapper_selection_only12_and13(self):
        select=namespace['select_request']
        self.assertEqual(select('local','useful'),'m1v14-local-work-12')
        self.assertEqual(select('local','continuation'),'m1v14-local-work-13')
        for lane,phase in (('connector','useful'),('local','replay')):
            with self.assertRaises(RuntimeError):select(lane,phase)

    def test_actual_failed_predecessor_guard_preserves_failed(self):
        validate=namespace['require_failed_predecessor']
        value={'scope':{'session_id':'old'},'lifecycle_state':'FAILED','lease_state':'CLOSED'}
        validate(value,'old')
        for change in ({'lifecycle_state':'CLOSED'},{'lease_state':'ACTIVE'},{'scope':{'session_id':'other'}}):
            with self.assertRaises(RuntimeError):validate(value|change,'old')

    def test_returned_stops_do_not_assert_physical_cleanup_or_interrupt(self):
        for codes in ([0],[3]):
            result=namespace['stop_attempt_projection'](codes)
            self.assertFalse(result['physical_exit_confirmed']);self.assertFalse(result['normal_cleanup_confirmed'])
            self.assertFalse(result['autonomous_interrupt_selected']);self.assertEqual(result['stop_wrapper_exits'],codes)

    def context(self,checkpoint):
        return SimpleNamespace(ROOT=Path(checkpoint['root']),args=SimpleNamespace(expected_proposal_sha256=checkpoint['proposal_sha256'],approval_sha256=checkpoint['authorization_sha256']),
            P={'controller_preparation':{'policy':checkpoint['policy'],'ancestry':checkpoint['ancestry']}})

    def test_real_closure_projection_carries11_not_fake_settlement(self):
        checkpoint=fixtures.prepare_derived(fixtures.CP,fixtures.CLOSED,fixtures.ACCOUNTING,source_pins=fixtures.BASIS)
        summary=close.checkpoint_summary(self.context(checkpoint),checkpoint,{'known_observed_tokens':0})
        self.assertEqual(summary['cumulative_reserved_admissions'],11)
        self.assertEqual(summary['cumulative_minimum_observed_tokens'],272648)
        self.assertEqual(summary['unsettled_requests'],0)
        self.assertEqual(summary['historical_original_unsettled_requests'],1)
        bad=deepcopy(checkpoint);bad['fresh_local_work']['historical_checkpoint']['requests']['m1v14-local-work-11']['settled']=True
        bad['state_sha256']=fixtures.seal(bad)
        with self.assertRaisesRegex(RuntimeError,'HISTORICAL_UNSETTLED'):close.checkpoint_summary(self.context(bad),bad,{'known_observed_tokens':0})

    def test_upgrade_is_finite_maintenance_not_model_admission(self):
        cp=fixtures.prepare_derived(fixtures.CP,fixtures.CLOSED,fixtures.ACCOUNTING,source_pins=fixtures.BASIS)
        context=self.context(cp);context.PUBLIC=CANDIDATE/'nonexistent-public'
        final={'tasks':{k:{'canonical_absence':{'state':'stopped','reason':'NO_SERVICE_OWNER'}} for k in ('nexus','connector')}}
        inventory={'upgrade-plan':{'mode':'upgrade','selection':['plan'],'returncode':0},'upgrade-apply':{'mode':'upgrade','selection':['apply'],'returncode':0}}
        summary=close.before_controller_summary(context,inventory,final)
        self.assertEqual(summary['new_reserved_admissions'],0);self.assertEqual(summary['cumulative_reserved_admissions'],11)
        inventory['bad']={'mode':'work','selection':['local','useful'],'returncode':0}
        with self.assertRaises(RuntimeError):close.before_controller_summary(context,inventory,final)

    def test_ready_gate_precedes_start_and_old_containment_not_imported(self):
        calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)]
        ready=[n.lineno for n in calls if n.func.attr=='require_ready']
        starts=[n.lineno for n in calls if n.func.attr=='start_work']
        self.assertEqual(len(ready),1);self.assertEqual(len(starts),1);self.assertLess(ready[0],starts[0])
        self.assertFalse(any(isinstance(n,ast.ImportFrom) and n.module=='containment_driver' for n in ast.walk(tree)))

if __name__=='__main__':unittest.main()
