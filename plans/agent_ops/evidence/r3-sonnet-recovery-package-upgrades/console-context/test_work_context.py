"""Small context deltas; temporary fixture files, no service/provider/vault IO."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
import subprocess
import importlib.util
import sys

from work_context import Context,ConsoleFuture,WORK_IDS,validate_completed,check_prior_reservations
from request_context import Refused

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.private=self.root/'private';self.public=self.root/'public';self.private.mkdir();self.public.mkdir()
    def tearDown(self):self.tmp.cleanup()
    def put(self,path,value):path.write_text(json.dumps(value));return path
    def test_completed_transfer_does_not_promote_review_profile(self):
        scope=dict(agent_id='subject',adapter_id='claude_stream',candidate_ref='selected')
        p=dict(profile='profile',server_id='server',agent_id='subject',candidate_ref='selected',operator_profile='human')
        c=dict(profile='profile',server_id='server',remote_scope=scope)
        t=dict(status='TRANSFERRED_ONCE',producer_exit=0,consumer_exit=0,active_job_processes_after=0,forced_owned_cleanup=False,public_ipc_readers_joined=True)
        doc=dict(state='review',server_id='server',remote_scope=scope,selection={'operator_profile':'human'})
        with self.assertRaisesRegex(Refused,'COMPLETED_REMOTE_SCOPE_CHANGED'):validate_completed(c,t,doc,p)
        doc['state']='done';self.assertEqual(validate_completed(c,t,doc,p),scope)
        doc['selection']['operator_profile']='participant'
        with self.assertRaisesRegex(Refused,'OPERATOR_PROFILE_CHANGED'):validate_completed(c,t,doc,p)
    def test_unknown_pre_receipt_reservation_blocks_next_work(self):
        rid=WORK_IDS['useful'];self.put(self.private/(rid+'-reserved.json'),{'request_id':rid})
        with self.assertRaisesRegex(Refused,'PREVIOUS_RESERVATION_UNCONFIRMED'):check_prior_reservations(self.private,self.public,WORK_IDS['continuation'],WORK_IDS)
        self.put(self.public/(rid+'-result.json'),dict(terminal_observed=True,canonical_succeeded=True,useful_result_confirmed=True))
        check_prior_reservations(self.private,self.public,WORK_IDS['continuation'],WORK_IDS)
        with self.assertRaisesRegex(Refused,'WORK_SELECTION_ALREADY_RESERVED'):check_prior_reservations(self.private,self.public,rid,WORK_IDS)
    def test_report_verification_is_actual_fixture_not_model_output_assumption(self):
        csv=self.root/'numbers.csv';csv.write_text('value\n3\n5\n')
        report=self.root/'report.json';digest=hashlib.sha256(csv.read_bytes()).hexdigest()
        ctx=Context.__new__(Context);ctx.P={'input_fixture':{'path':str(csv),'sha256':digest},'report':str(report)}
        self.put(report,dict(row_count=2,sum=8,input_sha256=digest));self.assertTrue(ctx.verify_useful())
        self.put(report,dict(row_count=2,sum=9,input_sha256=digest));self.assertFalse(ctx.verify_useful())
    def test_operator_alias_returns_same_updated_flow_instance(self):
        ctx=Context.__new__(Context);ctx._flow=SimpleNamespace(expected_session=None)
        self.assertIs(ctx.operator_flow(),ctx.work_flow())
        ctx.work_flow().expected_session='actual-submitted-session'
        self.assertEqual(ctx.operator_flow().expected_session,'actual-submitted-session')
    def test_normal_stop_timeout_retains_cli_and_never_starts_second_component(self):
        ctx=Context.__new__(Context);ctx.PRIVATE=self.private;ctx.PUBLIC=self.public;ctx.ROOT=self.root
        ctx.plan_sha256='fixture';ctx.handles={n:{'child':SimpleNamespace(exited=lambda:False)} for n in ('nexus','connector')}
        ctx.selected={n:{'cohort':{'fixture':n}} for n in ('nexus','connector')};ctx.children=[]
        ctx.P={'normal_stop_argv':{n:['python','stop','--timeout','45'] for n in ('nexus','connector')}}
        ctx.transfer=SimpleNamespace(connector_env=lambda:{});ctx._control_identity=lambda *a,**k:None
        child=SimpleNamespace(wait=lambda **kw:(_ for _ in ()).throw(subprocess.TimeoutExpired('fixture',180)))
        with patch('work_context.subprocess.Popen',return_value=child) as popen:
            result=ctx.normal_stop()
        self.assertTrue(result['pending_cli']);self.assertEqual(popen.call_count,1);self.assertIs(ctx.children[0],child)
    def test_handoff_requires_live_external_watchers_and_never_claims_settlement(self):
        ctx=Context.__new__(Context);ctx.PUBLIC=self.public;ctx.plan_sha256='fixture';ctx._last_request='request';ctx.selected={};ctx.children=[]
        ctx._all_exited=lambda:False;ctx._external_watchers=lambda:{'nexus':{'retained':True},'connector':{'retained':True}}
        result=ctx.handoff(None,{})
        self.assertTrue(result['retained']);self.assertFalse(result['provider_settlement_confirmed'])
        ctx._external_watchers=lambda:(_ for _ in ()).throw(Refused('EXTERNAL_WATCH_NOT_LIVE'))
        with self.assertRaisesRegex(Refused,'EXTERNAL_WATCH_NOT_LIVE'):ctx.handoff(None,{})
    def console_context(self):
        helper_path=Path('C:/Users/jpamb/AppData/Local/Temp/r3-svc09-console-watch-y0edb3e0/console_watch.py')
        spec=importlib.util.spec_from_file_location('qualified_console_fixture',helper_path);helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
        def pinned(p):return {'path':str(p),'sha256':hashlib.sha256(Path(p).read_bytes()).hexdigest()}
        ctx=Context.__new__(Context);ctx.PUBLIC=self.public;ctx.PRIVATE=self.private;ctx.children=[];ctx._last_request='work'
        home=self.root/'home';(home/'terminal/work').mkdir(parents=True);self.put(home/'terminal/work/profile.json',{'fixture':'checkpoint'})
        ctx.P={'profile':'profile','project':str(self.root),'operator_profile':'human','console_helper':pinned(helper_path),'python_executable':pinned(sys.executable)}
        ctx.base=SimpleNamespace(P={'paths':{'operator_home':str(home)}},env=lambda:{'SystemRoot':'C:/Windows'})
        flow=SimpleNamespace(timeout=30);flow.set_timeout=lambda n:setattr(flow,'timeout',n);ctx._flow=flow
        ctx._console_observation=lambda op:{'operation_id':op,'scope':{'session_id':'session'},'executor_stage':'DISPATCHED','admission_state':'ACCEPTED'}
        self.put(self.private/'work-admission.json',{'operation_id':'op'})
        self.put(self.private/'sonnet-budget.json',{'state':{'sessions':[{'active':'op','scope':{'session_id':'session','stream_epoch':'epoch'}}]}})
        return ctx,helper,flow
    def test_console_invisibility_is_inconclusive_without_cancel_or_approval(self):
        ctx,helper,flow=self.console_context();calls=[]
        def run(path,**kwargs):
            helper.validate(json.loads(Path(path).read_text()));calls.append(kwargs)
            return {'status':'INCONCLUSIVE_CONSOLE_CLOSURE','visible_before':False},None
        helper.run=run
        with patch('work_context.load_module',return_value=helper):ctx._console_hook('session')
        summary=json.loads((self.public/'svc09-console-summary.json').read_text())
        self.assertTrue(summary['same_operation_and_cohorts_active']);self.assertFalse(summary['svc09_acceptance'])
        self.assertEqual(flow.timeout,30);self.assertEqual(len(calls),1);self.assertLessEqual(calls[0]['wait_seconds'],8)
    def test_console_pending_runtime_propagates_owned_future_no_profile_reentry(self):
        from activecontrol import PendingWorker
        from concurrent.futures import TimeoutError
        ctx,helper,flow=self.console_context();child=SimpleNamespace(poll=lambda:None,returncode=None)
        helper.run=lambda *a,**k:({'status':'INCONCLUSIVE_CLI_STILL_RUNNING'},child)
        helper.api=lambda:(SimpleNamespace(),None)
        with patch('work_context.load_module',return_value=helper),patch('work_context.ConsoleFuture.result',side_effect=TimeoutError()):
            with self.assertRaises(PendingWorker) as caught:ctx._console_hook('session')
        self.assertIs(caught.exception.future.process,child);self.assertEqual(flow.timeout,30)
        self.assertIs(ctx.children[-1],caught.exception.future)
    def test_console_exception_after_retention_blocks_control_even_if_evidence_write_fails(self):
        from activecontrol import PendingWorker
        ctx,helper,flow=self.console_context();observed=[]
        original=ctx._console_observation
        ctx._console_observation=lambda op:observed.append(op) or original(op)
        child=SimpleNamespace(pid=41,poll=lambda:0,returncode=0)
        def run(path,*,retain_process,**kwargs):
            retain_process(child)
            raise OSError('synthetic metadata failure after launch')
        helper.run=run;helper.api=lambda:(SimpleNamespace(),None)
        with patch('work_context.load_module',return_value=helper),patch('work_context.atomic',side_effect=OSError('synthetic evidence failure')):
            with self.assertRaises(PendingWorker) as caught:ctx._console_hook('session')
        self.assertEqual(observed,['op'])  # No second profile read or control.
        self.assertIs(caught.exception.future.process,child)
        self.assertFalse(caught.exception.future.done())  # Launcher exit is insufficient.
        self.assertIn(caught.exception.future,ctx.children)
        self.assertEqual(flow.timeout,30)
    def test_console_future_needs_exact_runtime_birth_and_exit_after_launcher_exit(self):
        child=SimpleNamespace(pid=41,poll=lambda:0,returncode=0)
        metadata=self.root/'console-before.json';closed=[]
        kernel=SimpleNamespace(OpenProcess=lambda *a:77,CloseHandle=closed.append,WaitForSingleObject=lambda *a:0)
        future=ConsoleFuture(child,kernel,metadata,lambda *a:900)
        self.assertFalse(future.done())
        self.put(metadata,{'pid':42,'parent_pid':41,'birth':901})
        self.assertFalse(future.done());self.assertEqual(closed,[77])
        self.put(metadata,{'pid':42,'parent_pid':999,'birth':900})
        self.assertFalse(future.done())
        self.put(metadata,{'pid':42,'parent_pid':41,'birth':900})
        self.assertTrue(future.done());self.assertEqual(future.result(timeout=0),{'console_processes_exited':True})
        self.assertEqual(closed,[77,77]);self.assertTrue(future.done())
    def test_close_retains_unknown_console_without_new_control_or_false_exit(self):
        from concurrent.futures import TimeoutError
        ctx=Context.__new__(Context);ctx.PUBLIC=self.public;ctx.handles={}
        child=SimpleNamespace(pid=41,poll=lambda:0,returncode=0)
        future=ConsoleFuture(child,SimpleNamespace());ctx.children=[child,future]
        with patch.object(future,'result',side_effect=TimeoutError()) as wait:
            ctx.close()
        wait.assert_called_once_with(timeout=7200)
        value=json.loads((self.public/'console-retained-observation.json').read_text())
        self.assertEqual(value['state'],'RUNTIME_EXIT_UNKNOWN');self.assertFalse(value['new_control_selected'])
        with patch.object(future,'result',side_effect=TimeoutError()) as wait,patch('work_context.atomic',side_effect=OSError('synthetic disk error')):
            ctx.close()
        wait.assert_called_once_with(timeout=7200)

if __name__=='__main__':unittest.main(verbosity=2)
