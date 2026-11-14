import copy
import json
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE/'controller'))
from api_worker import EffectFence,SerialAPI,Fenced
from independent_controller import Controller
from resumed_controller import prepare_derived,validate_never_dispatched,ResumedController,REQUEST

SOURCE=Path('C:/Users/jpamb/AppData/Local/Temp/m1-v12-bundle-bldo9qy7/successor14')

def inputs():
    read=lambda path:json.loads(path.read_bytes())
    cp=read(SOURCE/'private/controller.json')
    result=read(SOURCE/'public/m1v14-local-work-01-result.json')
    closure=read(SOURCE/'public/closure.json')
    returned=read(SOURCE/'root-drivers/runtime-private/work-local-useful.returned.json')
    absence={'request_id':REQUEST,'server_id':cp['requests'][REQUEST]['scope']['server_id'],
             'actor_agent_id':'operator','canonical_intent_count':0}
    return cp,result,closure,absence,returned

class Clock:
    def __init__(self,value):
        self.value=value;self.owner=threading.get_ident();self.worker_seen=threading.Event()
    def __call__(self):
        if threading.get_ident()!=self.owner:self.worker_seen.set()
        return self.value

class Tests(unittest.TestCase):
    def worker(self,clock):
        fence=EffectFence(clock);fence.observation_required=True;fence.fresh_until=1
        fence.arm(600);api=SerialAPI(fence);calls=[]
        transport=api.transport(lambda *args:calls.append(args) or {'ok':True})
        return fence,api,calls,transport

    def test_1103ms_jitter_waits_then_dispatches_once_only_after_fresh_poll(self):
        clock=Clock(1.103);fence,api,calls,transport=self.worker(clock)
        api.submit('one',lambda:transport('POST','/resolve'),productive=True)
        self.assertTrue(clock.worker_seen.wait(5));self.assertEqual(calls,[])
        self.assertFalse(api.done.is_set());self.assertFalse(fence.event.is_set())
        fence.begin_poll(clock.value,.6);fence.end_poll(clock.value,True)
        self.assertTrue(api.done.wait(5));result=api.take()
        self.assertTrue(result['ok']);self.assertEqual(len(calls),1)
        self.assertEqual(fence.dispatched_effects,1)

    def test_cadence_1103ms_records_but_over5seconds_contains(self):
        controller=object.__new__(Controller);controller._lock=None
        controller._last_poll=0;controller._max_poll_interval=0
        controller.data={'requests':{'one':{'settled':False}}}
        faults=[];controller.fault=faults.append
        controller._record_poll_start(1.103)
        self.assertEqual(faults,[]);self.assertEqual(controller._max_poll_interval,1.103)
        controller._record_poll_start(6.104)
        self.assertEqual(faults,['MONITOR_CADENCE_EXCEEDED'])

    def test_stale_wait_has_one_600second_deadline_and_no_post(self):
        clock=Clock(1.103);fence,api,calls,transport=self.worker(clock)
        api.submit('one',lambda:transport('POST','/resolve'),productive=True)
        self.assertTrue(clock.worker_seen.wait(5));clock.value=600
        fence.observation_updated.set()
        self.assertTrue(api.done.wait(5));result=api.take()
        self.assertFalse(result['ok']);self.assertIsInstance(result['error'],Fenced)
        self.assertEqual(fence.reason,'DEADLINE600');self.assertEqual(calls,[])

    def test_tokens_and_poll_budget_remain_hard_effect_guards(self):
        for reason in ('PREVENTIVE_THRESHOLD','OBSERVATION_POLL_BUDGET_EXCEEDED'):
            with self.subTest(reason=reason):
                clock=Clock(1.103);fence,api,calls,transport=self.worker(clock)
                if reason=='PREVENTIVE_THRESHOLD':fence.known_tokens=500000
                else:fence.poll_deadline=1
                api.submit('one',lambda:transport('POST','/resolve'))
                self.assertTrue(api.done.wait(5));self.assertFalse(api.take()['ok'])
                self.assertEqual(fence.reason,reason);self.assertEqual(calls,[])

    def test_never_dispatched_proof_preserves_reservation_and_rejects_uncertainty(self):
        values=inputs();original=copy.deepcopy(values[0])
        derived=prepare_derived(*values,source_pins={'test':'real-source-fixture'})
        self.assertEqual(values[0],original);self.assertEqual(derived['collector'],original['collector'])
        self.assertEqual(derived['requests'][REQUEST]['started'],original['requests'][REQUEST]['started'])
        self.assertEqual(derived['pre_effect_resumption']['historical_faults'],original['faults'])
        self.assertEqual(derived['pre_effect_resumption']['cumulative_reserved_admissions'],10)
        for target,key,value in ((1,'calls',{'POST':1,'productive_posts':0,'decision_posts':0}),
                                 (3,'canonical_intent_count',1)):
            changed=copy.deepcopy(values);changed[target][key]=value
            with self.assertRaises(RuntimeError):validate_never_dispatched(*changed)

    def test_resumed_controller_reuses_reservation_and_persists_first_dispatch_once(self):
        derived=prepare_derived(*inputs(),source_pins={'test':'real-source-fixture'})
        with tempfile.TemporaryDirectory() as directory:
            control=Path(directory);private=control/'resume-request01/private';private.mkdir(parents=True)
            path=private/'controller.json';path.write_text(json.dumps(derived),encoding='utf-8')
            clock=Clock(100)
            with patch.object(ResumedController,'_approval_valid',return_value=True),\
                 patch.object(ResumedController,'_require_authorized',return_value=None):
                controller=ResumedController(path,derived['root'],original_control_root=control,
                    first_dispatch_receipt=private/'first-dispatch.json',monotonic=clock,
                    approval_sha256=derived['authorization_sha256'],
                    expected_proposal_sha256=derived['proposal_sha256'])
                before=copy.deepcopy(controller.data['collector'])
                controller._readers['local']=SimpleNamespace(read=lambda request:None)
                controller._journals['local']=SimpleNamespace(io=SimpleNamespace(failed=False))
                calls=[]
                transport=controller.api.transport(lambda *args:calls.append(args) or {'ok':True})
                controller.flows['local']=SimpleNamespace(submit=lambda *args,**kwargs:transport('POST','/resolve'))
                controller.fence.end_poll(clock.value,True)
                controller.start_work(REQUEST,'local','fixture',binding=derived['requests'][REQUEST]['scope'],
                    checkpoint={},new_session=True)
                self.assertTrue(controller.api.done.wait(5));result=controller.api.take()
                self.assertTrue(result['ok']);self.assertEqual(len(calls),1)
                self.assertEqual(controller.data['collector'],before)
                self.assertEqual(controller._execution_start(controller.data['requests'][REQUEST]),100)
                self.assertEqual(controller.fence.deadline,700)
                with self.assertRaisesRegex(RuntimeError,'ALREADY_RESUMED'):
                    controller.start_work(REQUEST,'local','fixture',binding={},checkpoint={},new_session=True)
                self.assertTrue((private/'first-dispatch.json').exists())
                controller._readers.clear();controller._journals.clear();controller.close()

if __name__=='__main__':unittest.main()
