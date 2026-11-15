from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import json
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parent))
from build_work_plan import convert_seed,FIX
from sonnet_usage import restore_budget,checkpoint_budget,Ledger,Unknown
from remote_work import effect_transport,run
from work_context import Context,WORK_IDS,sha


class SuccessorTests(unittest.TestCase):
    def setUp(self):
        self.original=json.loads((FIX/'reconciled-budget.json').read_bytes())
        self.converted=convert_seed(self.original)

    def test_policy_conversion_preserves_all_usage_and_charge_fields(self):
        before=deepcopy(self.original['state']);after=deepcopy(self.converted['state'])
        after['preventive']=before['preventive']
        for old,new in zip(before['sessions'],after['sessions']):new['preventive']=old['preventive']
        self.assertEqual(before,after)
        budget=restore_budget(self.converted)
        self.assertEqual((budget.known,budget.preventive),(36306,180000))
        self.assertEqual(budget.check_admission('useful')['reserved_next'],102046)

    def test_context_rejects_missing_history_even_with_same_total(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'seed.json';path.write_text(json.dumps(self.converted))
            context=SimpleNamespace(P={'budget_seed':{'path':str(path),'sha256':sha(path)}})
            budget=restore_budget(self.converted)
            Context.validate_budget(context,budget)
            next(iter(budget.sessions.values())).reserved=['replacement']
            with self.assertRaises(RuntimeError):Context.validate_budget(context,budget)

    def test_roundtrip_with98_sequence_keys_and_tamper_refused(self):
        budget=restore_budget(json.loads(json.dumps(self.converted)))
        self.assertEqual(len(next(iter(budget.sessions.values())).seen),98)
        roundtrip=json.loads(json.dumps(checkpoint_budget(budget)))
        self.assertEqual(restore_budget(roundtrip).known,36306)
        changed=deepcopy(self.original);changed['state']['sessions'][0]['known']+=1
        with self.assertRaises(RuntimeError):convert_seed(changed)
        changed=deepcopy(roundtrip);changed['state']['sessions'][0]['seen']['10']='tampered'
        with self.assertRaises(Unknown):restore_budget(changed)

    def test_effect_boundary_uses_selected180_not_old150(self):
        budget=SimpleNamespace(known=170000,preventive=180000,sessions={})
        calls=[];state={'monitor':None,'started':0,'containment':False,'budget':budget}
        guarded=effect_transport(lambda *args:calls.append(args),state,clock=lambda:1)
        guarded('POST','/synthetic',{})
        self.assertEqual(len(calls),1)
        budget.known=180000
        with self.assertRaises(Unknown):guarded('POST','/synthetic',{})
        self.assertEqual(len(calls),1)

    def test_global_three_includes_historical_charge(self):
        budget=restore_budget(self.converted)
        scope=dict(next(iter(budget.sessions.values())).scope,session_id='new',stream_epoch='new')
        current=Ledger(scope,preventive=budget.preventive);budget.attach(current)
        budget.reserve(current,'new-useful',phase='useful')
        self.assertEqual(current.preventive,180000)
        current.active=None;current.terminal_coverage=True
        budget.reserve(current,'new-continuation',phase='continuation')
        current.active=None;current.terminal_coverage=True
        with self.assertRaises(Unknown):budget.check_admission('continuation')
        self.assertEqual(sum(len(row.reserved) for row in budget.sessions.values()),3)

    def test_missing_seed_refuses_before_dispatch(self):
        with tempfile.TemporaryDirectory() as directory:
            context=SimpleNamespace(require_ready=lambda:None,request_ids=WORK_IDS,
                                    PRIVATE=Path(directory),PUBLIC=Path(directory))
            with self.assertRaisesRegex(Unknown,'MANDATORY_RECONCILED_BUDGET_MISSING'):
                run(context,'useful')
            self.assertEqual(list(Path(directory).iterdir()),[])

    def test_new_cli_session_does_not_require_erasing_checkpoint(self):
        from okto_nexus.application.terminal_work import TerminalWork
        scope={k:k for k in ('server_id','executor_id','binding_id','agent_id','workspace_id','workspace_binding_id')}
        old={'format':1,'scope':scope,'session_id':'old-session',
             'work':{'state':'admitted','action':'send','client_intent_id':'old-request'}}
        saved=[];posts=[]
        flow=TerminalWork(None,saved.append,{},old)
        flow.binding=lambda:scope
        def api(method,path,body=None):
            posts.append((method,path,body))
            return {'client_intent_id':body['client_intent_id'],'operation_id':'new-open',
                'resolution_revision':1,'intent_hash':'exact','semantic_intent':{'action':'runtime.open'},
                'scope':dict(scope,session_id='new-session'),'session_id':'new-session',
                'can_submit':True,'blockers':[]}
        flow.api=api;flow._admit=lambda slot,binding:{'session':flow.document['session_id']}
        result=flow.submit('synthetic',new_session=True,client_intent_id=WORK_IDS['useful'])
        self.assertEqual(result['session'],'new-session')
        self.assertEqual(posts[0][2]['intent'],'runtime.start')
        self.assertTrue(posts[0][2]['new_session'])
        self.assertNotIn('session_id',posts[0][2])
        self.assertEqual(old['session_id'],'old-session')
        self.assertEqual(len(posts),1)


if __name__=='__main__':unittest.main()
