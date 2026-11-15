from pathlib import Path
import copy
from datetime import datetime, timezone
import json
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).parent))
import driver
import usage


class PureDriverTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='home-r1-local-codex-test-')
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.d=object.__new__(driver.Driver)
        self.d.root=self.root; self.d.home=self.root/'nexus-home'
        self.d.private=self.root/'private'; self.d.private.mkdir()
        self.d.public=self.root/'public'; self.d.public.mkdir()
        self.d.plan_sha='p'; self.d.p={'campaign_id':'home-r1-test','campaign_root':str(self.root)}; self.d.work_args=[]; self.d.common=[]; self.d.p.update(codex_candidate_ref='synthetic-ref',provider_home=str(self.root/'synthetic-provider-home'))

    def consent(self):
        return {'user_authorized_paid_campaign':True,'user_response_reference':'test-only synthetic',
                'campaign_id':'home-r1-test','campaign_root':str(self.root),'candidate_sha256':'p','policy':driver.POLICY,'acknowledges_delayed_usage_overshoot':True}

    def test_missing_consent_refuses_before_process_or_product(self):
        path=self.root/'consent.json'; path.write_text('{}')
        plan={'policy':driver.POLICY,'campaign_id':'home-r1-test','consent':{'path':str(path),'sha256':driver.sha(path)}}
        selected=self.root/'plan.json'; selected.write_text(json.dumps(plan))
        with patch('subprocess.Popen') as spawn, patch.object(driver.Driver,'product') as product:
            with self.assertRaisesRegex(ValueError,'NEW_PAID_CONSENT'):
                driver.Driver(selected,driver.sha(selected),tests=True)
            spawn.assert_not_called(); product.assert_not_called()

    def test_consent_scope_limits_and_delayed_usage_are_exact(self):
        c=self.consent(); driver.consent_valid(self.d.p,c,'p')
        for field,value in [('campaign_id','other'),('candidate_sha256','different'),('campaign_root',str(self.root/'other')),('user_authorized_paid_campaign',1),
                            ('acknowledges_delayed_usage_overshoot',False),('policy',{'max_calls':3})]:
            altered={**c,field:value}
            with self.assertRaises(ValueError):driver.consent_valid(self.d.p,altered,'p')

    def test_setup_reservation_is_unique_even_after_unknown(self):
        self.d.reserve('setup')
        first=(self.d.private/'call-setup-reserved.json').read_bytes()
        with self.assertRaises(ValueError):self.d.reserve('setup')
        self.assertEqual(first,(self.d.private/'call-setup-reserved.json').read_bytes())
        with self.assertRaises(FileNotFoundError):self.d.reserve('useful')
        self.assertFalse((self.d.private/'call-useful-reserved.json').exists())

    def test_complete_setup_allows_only_second_reservation(self):
        self.d.reserve('setup')
        driver.publish(self.d.public/'setup-accounting-final.json',{
            'plan_sha256':'p','terminal_usage_covered':True,'observed_total':1200})
        self.d.reserve('useful')
        with self.assertRaisesRegex(ValueError,'CALL_LIMIT'):self.d.reserve('useful')
        self.assertEqual(len(list(self.d.private.glob('call-*-reserved.json'))),2)

    def test_unknown_or_budget_reached_blocks_second(self):
        self.d.reserve('setup')
        path=self.d.public/'setup-accounting-final.json'
        for usage_doc in [{'terminal_usage_covered':False,'observed_total':2},
                          {'terminal_usage_covered':True,'observed_total':150000}]:
            path.write_text(json.dumps({'plan_sha256':'p',**usage_doc}))
            with self.assertRaisesRegex(ValueError,'USAGE_UNKNOWN_OR_BUDGET'):self.d.reserve('useful')
            self.assertFalse((self.d.private/'call-useful-reserved.json').exists())

    def test_atomic_publish_never_overwrites_or_consumes_partial(self):
        path=self.root/'receipt.json'; path.with_suffix('.json.writing').write_text('incomplete')
        with self.assertRaises(FileExistsError):driver.publish(path,{'ok':True})
        self.assertFalse(path.exists())
        path2=self.root/'second.json'; driver.publish(path2,{'ok':True})
        with self.assertRaisesRegex(ValueError,'ALREADY_SELECTED'):driver.publish(path2,{'ok':False})
        self.assertTrue(driver.read(path2)['ok'])

    def grant(self):
        scope={k:k for k in ('server_id','executor_id','binding_id','workspace_id','agent_id','workspace_binding_id','endpoint_id')}
        grant={'grant_id':'g','revision':1,'state':'available','actions':['open','send','interrupt','close'],
               'expires_at':'2099-01-01T00:00:00Z','max_executions':5,'used_executions':0}
        return scope,{'state':'authorization_review','can_issue':False,'scope':scope,'current_grants':[grant]}

    def test_grant_current_scope_expiry_actions_and_capacity(self):
        scope,review=self.grant(); now=datetime.now(timezone.utc)
        self.assertEqual(driver.available_grant(review,scope,now)['grant_id'],'g')
        for key,value in [('state','expired'),('expires_at','2000-01-01T00:00:00Z'),
                          ('actions',['open']),('used_executions',2)]:
            changed=copy.deepcopy(review); changed['current_grants'][0][key]=value
            with self.assertRaisesRegex(ValueError,'CURRENT_GRANT'):driver.available_grant(changed,scope,now)
        with self.assertRaisesRegex(ValueError,'GRANT_SCOPE'):
            driver.available_grant(review,{**scope,'agent_id':'other'},now)

    def test_no_useful_post_or_reservation_without_available_grant(self):
        (self.root/'deliverables').mkdir(); (self.root/'workspace').mkdir()
        file=self.root/'workspace/numbers.csv'; file.write_bytes(b'value\n1\n')
        driver.publish(self.d.public/'setup-complete.json',{'configured':True})
        driver.publish(self.d.public/'prepared.json',{'input_sha256':driver.sha(file)})
        driver.publish(self.d.public/'setup-accounting-final.json',{'observed_total':10})
        scope,review=self.grant(); review['can_issue']=True
        class Flow:
            def binding(self):return scope
        calls=[]
        with patch.object(self.d,'watched'),patch.object(self.d,'setup_usage',return_value={'terminal_usage_covered':True,'observed_total':10}),patch.object(self.d,'flow',return_value=Flow()),                patch.object(self.d,'cli',side_effect=lambda label,argv,**kw:(calls.append(label) or (0,review))):
            with self.assertRaisesRegex(ValueError,'CURRENT_GRANT'):self.d.useful()
        self.assertEqual(calls,['grant-review'])
        self.assertFalse((self.d.private/'call-useful-reserved.json').exists())

    def test_finished_resume_is_read_only_no_new_send(self):
        driver.publish(self.d.private/'call-useful-reserved.json',{'kind':'useful'})
        scope={'session_id':'s'}
        driver.publish(self.d.public/'useful-accounting-final.json',{
            'scope':scope,'canonical_state':'completed','observed_total':10})
        with patch.object(self.d,'current_scope',return_value=(None,None,{'state':'completed','events':{'stream_epoch':'e'}},scope)),                patch.object(self.d,'useful_usage',return_value={'observed_total':10,'terminal_usage_covered':True}),                patch.object(self.d,'cli') as cli:
            self.d.monitor();cli.assert_not_called()
        self.assertEqual(len(list(self.d.private.glob('call-*-reserved.json'))),1)

    def test_input_report_is_independently_decimal_checked(self):
        (self.root/'workspace').mkdir(); (self.root/'deliverables').mkdir()
        inp=self.root/'workspace/numbers.csv'; inp.write_bytes(b'value\n1.25\n2.50\n-0.75\n7.00\n')
        driver.publish(self.d.public/'prepared.json',{'input_sha256':driver.sha(inp)})
        out=self.root/'deliverables/report.json'
        out.write_text(json.dumps({'row_count':4,'sum':'10.00','input_sha256':driver.sha(inp)}))
        self.d.verify_report()
        self.assertTrue(driver.read(self.d.public/'report-verification.json')['independent_decimal_check'])

    def test_path_escape_rejected(self):
        with self.assertRaisesRegex(ValueError,'OUTSIDE_OWN_ROOT'):usage.owned(self.root,self.root.parent/'other.db')

    def test_fresh_inventory_uses_runtime_options_and_separate_local_byte_proof(self):
        native=self.root/'codex.exe';native.write_bytes(b'own synthetic native bytes')
        self.d.p.update(codex_content_fingerprint=driver.sha(native),codex_executable=str(native),codex_candidate_ref='c')
        request={'executor_id':'exec','inventory_revision':'r','candidate_ref':'c','agent_creation':{},'agent_id':'new'}
        view={'adapter_freshness':{'codex_app_server':'FRESH'},'inventory_revision':'r',
              'options':[{'adapter_id':'codex_app_server','candidate_ref':'c','can_configure':True,'harness_configuration':{}}]}
        paths=[]
        def get(path):
            paths.append(path)
            return {'agent_id':'operator'} if path.endswith('/connections/me') else view
        with patch.object(self.d,'get',side_effect=get):self.assertEqual(self.d.inventory_for(request)['freshness'],'FRESH')
        self.assertTrue(paths[-1].startswith('/api/v1/runtime-management/agents/'))
        self.assertIn('/runtime-options?',paths[-1]);self.assertNotIn('/inventory',paths[-1])
        view['adapter_freshness']['codex_app_server']='STALE'
        with patch.object(self.d,'get',side_effect=get),self.assertRaisesRegex(ValueError,'INVENTORY_NOT_FRESH'):
            self.d.inventory_for(request)

    def test_paid_fast_invalid_json_enters_cleanup_without_retry(self):
        driver.publish(self.d.private/'selected-review.json',{'review_revision':'review','review_request':{}})
        class FakeChild:
            def __init__(inner,argv,**kw):kw['stdout'].write(b'{invalid');kw['stdout'].flush()
            def poll(inner):return 0
            def wait(inner,timeout=None):return 0
        with patch.object(self.d,'watched'),patch.object(self.d,'inventory_for'),                patch.object(driver.subprocess,'Popen',FakeChild),patch.object(self.d,'cleanup') as cleanup:
            with self.assertRaisesRegex(ValueError,'CLI_OUTPUT_UNCONFIRMED'):self.d.setup('review')
            cleanup.assert_called_once()
        self.assertTrue((self.d.private/'call-setup-reserved.json').exists())
        self.assertTrue(driver.read(self.d.public/'paid-setup-fault.json')['admissions_closed'])
        self.assertEqual(driver.read(self.d.public/'setup-returned.json')['outcome'],'UNCONFIRMED')
        with self.assertRaisesRegex(ValueError,'PAID_CAMPAIGN_CLOSED'):self.d.reserve('useful')

    def test_paid_fast_nonterminal_setup_also_enters_cleanup(self):
        driver.publish(self.d.private/'selected-review.json',{'review_revision':'review','review_request':{}})
        class FakeChild:
            def __init__(inner,argv,**kw):kw['stdout'].write(b'{"state":"test_running"}');kw['stdout'].flush()
            def poll(inner):return 0
            def wait(inner,timeout=None):return 0
        with patch.object(self.d,'watched'),patch.object(self.d,'inventory_for'),                patch.object(driver.subprocess,'Popen',FakeChild),                patch.object(self.d,'setup_usage',return_value={'observed_total':3,'terminal_usage_covered':False}),                patch.object(self.d,'cleanup') as cleanup:
            with self.assertRaisesRegex(ValueError,'SETUP_NOT_COVERED'):self.d.setup('review')
            cleanup.assert_called_once()
        self.assertFalse(driver.read(self.d.public/'setup-accounting-final.json')['terminal_usage_covered'])
        self.assertTrue((self.d.private/'paid-setup-containment-selected.json').exists())

    def test_capture_revalidates_birth_and_closes_partial_handles(self):
        import own_process
        image=self.root/'synthetic-python.exe';image.write_bytes(b'synthetic')
        self.d.p['python_images']={str(image):driver.sha(image)}
        status={'state':'ready','pid':3,'instance_id':'own','generation':'g'}
        cycle={'cycle_id':'c','phase':'running','attempts_started':1,'child_acknowledged':True,
               'parent':{'pid':1,'birth':11},'launcher':{'pid':2,'birth':22},'child':{'pid':3,'birth':33}}
        opened=[]
        class Handle:
            def __init__(inner,pid):inner.pid=pid;inner.birth=pid*11;inner.image=str(image);inner.closed=False;opened.append(inner)
            def close(inner):inner.closed=True
            def exited(inner):return False
        with patch.object(self.d,'status',return_value=status),patch.object(self.d,'cycle',return_value=cycle),patch.object(own_process,'Process',Handle):
            selected,handles=self.d.capture()
            self.assertEqual(set(handles),set(driver.ROLES))
            for handle in handles.values():handle.close()
        changed=copy.deepcopy(cycle);changed['child']['birth']=999
        with patch.object(self.d,'status',return_value=status),patch.object(self.d,'cycle',return_value=changed),patch.object(own_process,'Process',Handle):
            with self.assertRaisesRegex(ValueError,'PROCESS_BIRTH_OR_IMAGE_CHANGED'):self.d.capture()
        self.assertTrue(all(h.closed for h in opened))

    def test_cleanup_force_revalidates_current_own_generation_not_old_pid(self):
        from types import SimpleNamespace
        from okto_nexus.adapters.outbound.service_manager import installation
        self.d.p['own_cleanup_force_within_standing_stop_authority']=True
        forced=False;removed=False;calls=[];clock=[0]
        class Handle:
            pid=1;birth=2
            def exited(inner):return forced
            def exit_code(inner):return 0
            def close(inner):pass
        def capture():
            generation='new-generation' if calls else 'old-generation'
            return {'owner':{'generation':generation}}, {r:Handle() for r in driver.ROLES}
        def cli(label,argv,**kw):
            nonlocal forced,removed
            calls.append((label,argv))
            if label=='stop-force':forced=True
            if label=='uninstall':removed=True
            return 0,{}
        def tick():clock[0]+=61;return clock[0]
        fake=SimpleNamespace(observe=lambda:(None,None if removed else SimpleNamespace(active=False,state=3)))
        with patch.object(self.d,'status',side_effect=lambda:{'state':'stopped' if forced else 'stopping'}),                patch.object(self.d,'capture',side_effect=capture),patch.object(self.d,'current_scope',side_effect=ValueError('no binding')),                patch.object(self.d,'cli',side_effect=cli),patch.object(installation,'ServerInstallation',return_value=fake),                patch.object(driver.time,'monotonic',side_effect=tick),patch.object(driver.time,'sleep'):
            self.d.cleanup()
        force=[argv for label,argv in calls if label=='stop-force']
        self.assertEqual(len(force),1)
        self.assertEqual(force[0][force[0].index('--expected-generation')+1],'new-generation')
        self.assertTrue(driver.read(self.d.public/'cleanup.json')['physical_exit_confirmed'])
        self.assertTrue(removed)

    def test_stopped_without_retained_exit_proof_never_uninstalls(self):
        with patch.object(self.d,'status',return_value={'state':'stopped'}),patch.object(self.d,'cli') as cli:
            with self.assertRaises(FileNotFoundError):self.d.cleanup()
            cli.assert_not_called()


class UsageTests(unittest.TestCase):
    def rows(self):
        base={'thread_id':'t','turn_id':'u','phase':None,'outcome':None,'usage':None}
        return [{**base,'native_type':'turn/started','phase':'started'},
                {**base,'native_type':'thread/tokenUsage/updated','usage':{'totalTokens':100,'inputTokens':80,
                    'cachedInputTokens':60,'outputTokens':20,'reasoningOutputTokens':5}},
                {**base,'native_type':'turn/completed','phase':'terminal','outcome':'success'}]

    def summary(self,rows=None,**kw):
        return usage.summarize(self.rows() if rows is None else rows,
            **({'watermark':3,'count':3,'minimum':1,'maximum':3,'compacted':0}|kw))

    def test_cache_and_reasoning_subsets_not_double_counted(self):
        value=self.summary();self.assertEqual(value['observed_total'],100)
        self.assertTrue(value['terminal_usage_covered']);self.assertFalse(value['billing_final'])

    def test_missing_usage_terminal_and_watermark_never_zero_complete(self):
        value=self.summary([self.rows()[0],self.rows()[2]])
        self.assertFalse(value['terminal_usage_covered']);self.assertFalse(value['usage_seen'])
        with self.assertRaisesRegex(ValueError,'COVERAGE_GAP'):self.summary(count=2)
        with self.assertRaisesRegex(ValueError,'COVERAGE_GAP'):self.summary(compacted=1)

    def test_counter_regression_and_unexpected_second_call_fail(self):
        rows=self.rows();regressed=copy.deepcopy(rows[1]);regressed['usage']['totalTokens']=99
        with self.assertRaisesRegex(ValueError,'USAGE_REGRESSION'):self.summary(rows[:2]+[regressed]+rows[2:])
        second={**rows[0],'turn_id':'second'}
        with self.assertRaisesRegex(ValueError,'UNEXPECTED_NATIVE_CALL'):self.summary(rows+[second])

    def test_real_sql_projection_ro_exact_scope_no_payload_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/'journal.db'
            with sqlite3.connect(path) as db:
                db.execute('CREATE TABLE event_streams(server_id,executor_id,session_id,stream_epoch,next_sequence,compacted_sequence)')
                db.execute('CREATE TABLE events(server_id,executor_id,session_id,stream_epoch,sequence,body)')
                db.execute('INSERT INTO event_streams VALUES(?,?,?,?,?,?)',('srv','ex','s','e',4,0))
                for i,r in enumerate(self.rows(),1):
                    body={'native_type':r['native_type'],'payload':{'thread_id':'t','turn_id':'u',
                        'delivery_phase':r['phase'],'delivery_outcome':r['outcome'],'tokenUsage':{'total':r['usage']},
                        'output_text':'SENTINEL_DO_NOT_EXPORT'}}
                    db.execute('INSERT INTO events VALUES(?,?,?,?,?,?)',('srv','ex','s','e',i,json.dumps(body)))
            db.close()
            before=driver.sha(path)
            value=usage.journal_snapshot(root,path,('srv','ex','s','e'))
            self.assertEqual(before,driver.sha(path));self.assertEqual(value['observed_total'],100)
            self.assertNotIn('SENTINEL',json.dumps(value))
            with self.assertRaisesRegex(ValueError,'STREAM_NOT_YET_AVAILABLE'):
                usage.journal_snapshot(root,path,('srv','ex','OTHER','e'))


class BinderTests(unittest.TestCase):
    def test_candidate_without_consent_is_text_only_and_execute_refuses(self):
        import bind_plan
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);native=root/'codex.exe';native.write_bytes(b'synthetic native fixture, never executed')
            before=set(root.iterdir())
            package={'python':{'path':sys.executable,'sha256':'fixture'},'python_images':{},
                     'package':{'wheel':{'sha256':bind_plan.FINAL_WHEEL_SHA},'payload_pins':[]}}
            with patch('subprocess.Popen') as spawn,patch.object(driver.Driver,'product') as product:
                candidate=bind_plan.make_candidate(campaign_parent=root,port=62817,package=package,
                    codex_root=root,codex_executable=native,codex_sha256=driver.sha(native))
                path=root/'candidate.json';driver.publish(path,candidate)
                self.assertEqual(set(root.iterdir())-before,{path})
                self.assertFalse(Path(candidate['campaign_root']).exists())
                self.assertNotIn('consent',candidate)
                with self.assertRaisesRegex(ValueError,'NEW_PAID_CONSENT'):
                    driver.Driver(path,driver.sha(path),tests=True)
                spawn.assert_not_called();product.assert_not_called()

    def test_authorization_is_only_delta_and_cannot_rebind_family_or_namespace(self):
        import bind_plan
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);candidate={'artifact_kind':'INERT_TECHNICAL_CANDIDATE','campaign_id':'home-r1-local-codex-fixed',
                'campaign_root':str(root/'fixed'),'policy':driver.POLICY,'request_ids':{'useful':driver.USEFUL_ID},
                'package':{'wheel':{'sha256':bind_plan.FINAL_WHEEL_SHA}}}
            path=root/'candidate.json';driver.publish(path,candidate);before=path.read_bytes();digest=driver.sha(path)
            out=root/'authorization.json'
            record=bind_plan.authorize_candidate(path,digest,user_response_reference='SYNTHETIC_TEST_ONLY',
                    acknowledges_delayed_usage_overshoot=True,output=out)
            self.assertEqual(path.read_bytes(),before)
            self.assertEqual(set(root.iterdir()),{path,out})
            driver.consent_valid(candidate,record,digest)
            other={**candidate,'campaign_id':'other','campaign_root':str(root/'other')}
            with self.assertRaisesRegex(ValueError,'NEW_PAID_CONSENT'):driver.consent_valid(other,record,digest)
            family={**record,'campaign_family':'HOME-033-local-Codex','campaign_id':None}
            with self.assertRaisesRegex(ValueError,'NEW_PAID_CONSENT'):driver.consent_valid(candidate,family,digest)
            with self.assertRaisesRegex(ValueError,'NEW_PAID_CONSENT'):driver.consent_valid(candidate,record,'different-candidate')


class InstalledParserTests(unittest.TestCase):
    """Run installed parsers, interrupt at the first product/transport boundary; zero dispatch."""
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.common=['--home',str(self.root/'home'),'--host','127.0.0.1','--port','62817',
                     '--harness-root',str(self.root)]

    def test_runtime_options_route_is_actually_mounted_for_dashboard(self):
        from okto_nexus.adapters.inbound.http.dashboard_runtime import build_router
        paths={route.path for route in build_router().routes}
        self.assertIn('/agents/{agent_id}/runtime-options',paths)
        self.assertNotIn('/runtime/executors/{executor_id}/inventory',paths)

    def test_actual_work_parser_accepts_finite_argv_before_boundary(self):
        from okto_nexus.adapters.inbound.cli import work,terminal_target
        options=[['send','--new-session','--request-id','home-r1-local-useful-02','--message','synthetic'],
                 ['interrupt','--session-id','s','--request-id','i'],['close','--session-id','s','--request-id','c'],
                 ['authorize','--minutes','60','--actions','3'],['status']]
        for argv in options:
            with patch.object(terminal_target,'terminal_target_selection',side_effect=RuntimeError('TEST_BOUNDARY')) as target:
                with self.assertRaisesRegex(RuntimeError,'TEST_BOUNDARY'):
                    work.run_work([*argv,'--profile','home-r1-local','--project',str(self.root),
                                   '--readiness-timeout','5','--json',*self.common])
                target.assert_called_once()

    def test_actual_service_parser_accepts_scoped_force_and_install(self):
        from okto_nexus.adapters.inbound.cli import service
        for argv in [['install','--user','--start-at-login'],['start','--timeout','45'],
                     ['stop','--force','--expected-generation','generation','--timeout','45'],['uninstall','--user']]:
            with patch.object(service,'resolve_local_service',side_effect=RuntimeError('TEST_BOUNDARY')) as resolver:
                with self.assertRaisesRegex(RuntimeError,'TEST_BOUNDARY'):
                    service.run_service([*argv,'--json',*self.common])
                resolver.assert_called_once()

    def test_actual_connect_parser_review_and_apply_before_resolver(self):
        from okto_nexus.adapters.inbound.cli import connect
        for mode in [['--plan'],['--approve','review']]:
            with patch.object(connect,'resolve_local_service',side_effect=RuntimeError('TEST_BOUNDARY')) as resolver:
                with self.assertRaisesRegex(RuntimeError,'TEST_BOUNDARY'):
                    connect.run_connect([*mode,'--profile','home-r1-local','--new-agent','home-r1-local-worker',
                        '--name','Home R1 worker','--client','codex','--project',str(self.root),
                        '--provider-home',str(self.root/'synthetic-provider-home'),'--no-chat','--json',*self.common])
                resolver.assert_called_once()


if __name__=='__main__':unittest.main()
