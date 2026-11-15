"""Recovery receipt chain against installed DONE projection; no external IO."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
R=Path('C:/Users/jpamb/AppData/Local/Temp/sonnet-canonical-recovery-proposal-7oq808_t')
sys.path.insert(0,str(HERE));sys.path.insert(0,str(R))
import work_context as wc
import recovery_binding as guards
from recovery_context import Refused as RecoveryRefused
import test_recovery_binding as binding_fixtures


class Tests(unittest.TestCase):
    def setUp(self):
        fixture=binding_fixtures.Tests();fixture.setUp()
        self.binding,self.draft=fixture.p,fixture.draft
        self.doc=fixture.document();p=self.binding
        from okto_nexus.application.remote_terminal_setup import RemoteProjectSetup
        binding={k:p[k] for k in ('server_id','agent_id','workspace_id')}
        binding.update(state='APPROVED',executor_id='executor',binding_id='binding',workspace_binding_id='wb',
                       adapter_id='claude_stream',candidate_ref=self.draft['installation']['candidate_ref'])
        self.doc['final_binding']={k:binding[k] for k in ('server_id','agent_id','workspace_id','executor_id','binding_id')}
        self.doc['final_binding'].update(proposal_id='proposal',finish_id='proposal_setup')
        RemoteProjectSetup(lambda *a:binding,lambda *a:None,origin='http://127.0.0.1:58631')._complete(self.doc)
        self.plan={k:p[k] for k in ('profile','server_id','agent_id','operator_profile')}
        self.plan.update(candidate_ref=binding['candidate_ref'],binding_plan={'sha256':'binding-plan'},
            recovery_plan={'sha256':'lifecycle-plan'},prerequisites={
                'rotation_result':{'path':'rotation','sha256':'rotation-hash','bytes':42},
                'canonical_review':{'path':'review','sha256':'review-hash','bytes':42},
                'rotation_authority':{'path':'authority','sha256':'authority-hash'}})
        self.rotation=dict(status='ROTATED_ONCE_IMPORTED_ONCE',agent_id=p['agent_id'],server_id=p['server_id'],
            old_epoch=1,current_epoch=2,rotation_post_count=1,consumer_count=1,
            original_transfer_preserved_unconfirmed=True,old_profile_replayed=False,provider_turns=0,
            protected_transfer=dict(status='TRANSFERRED_ONCE',producer_exit=0,consumer_exit=0,
                active_job_processes_after=0,forced_owned_cleanup=False,public_ipc_readers_joined=True,
                effect_guard_required=True,effect_gates_allowed=['producer','consumer']),
            rotation_plan_sha256=p['rotation_plan']['sha256'],authorization_receipt_sha256='authority-hash',
            lifecycle_plan_sha256='lifecycle-plan')
        self.review=dict(profile=p['profile'],binding_plan_sha256='binding-plan',lifecycle_plan_sha256='lifecycle-plan',
            rotation_import_result_pin={'path':'rotation','sha256':'rotation-hash'},current_credential_epoch=2,
            review_revision=self.doc['review_revision'],review=self.doc['remote_review'])
        self.completed=dict(profile=p['profile'],server_id=p['server_id'],remote_scope=self.doc['remote_scope'],
            binding_plan_sha256='binding-plan',lifecycle_plan_sha256='lifecycle-plan',current_credential_epoch=2,
            rotation_import_result_pin={'path':'rotation','sha256':'rotation-hash'},
            canonical_review_pin={'path':'review','sha256':'review-hash'},
            profile_review_revision=self.doc['review_revision'],material_status='reuse_existing')

    def validate(self):
        return wc.validate_completed(self.completed,self.rotation,self.doc,self.plan,self.review,self.binding,self.draft,guards)

    def test_installed_done_epoch_two_chain_accepts_without_renaming_old_failure(self):
        with patch('subprocess.Popen',side_effect=AssertionError('no process')):
            self.assertEqual(self.validate(),self.doc['remote_scope'])
        self.assertTrue(self.rotation['original_transfer_preserved_unconfirmed'])

    def test_changed_approval_rotation_epoch_and_review_chain_refuse(self):
        for obj,key,value in ((self.rotation,'current_epoch',1),(self.rotation,'authorization_receipt_sha256','other'),
            (self.completed,'binding_plan_sha256','other'),(self.review,'profile','setup01'),
            (self.completed,'rotation_import_result_pin',{'path':'other','sha256':'rotation-hash'}),
            (self.completed,'canonical_review_pin',{'path':'review','sha256':'other'})):
            original=deepcopy(obj[key]);obj[key]=value
            with self.subTest(key=key),self.assertRaises((wc.require.__globals__['Refused'],RecoveryRefused)):
                self.validate()
            obj[key]=original

    def test_ready_or_binding_alone_does_not_replace_done_finish(self):
        self.doc['state']='awaiting_finish'
        with self.assertRaisesRegex(RecoveryRefused,'CANONICAL_DONE_BINDING_REQUIRED'):self.validate()
        self.doc['state']='done';self.doc['final_binding']['finish_id']='unrelated'
        with self.assertRaisesRegex(RecoveryRefused,'FINAL_FINISH_SCOPE_UNCONFIRMED'):self.validate()

    def test_new_recovery_context_uses_both_ready_owners_without_paid_effect(self):
        # Real new package constructor verifies its installation and lifecycle pins.
        from recovery_context import RecoveryContext,sha
        with patch('subprocess.Popen',side_effect=AssertionError('no process')):
            actual=RecoveryContext(R/'lifecycle-plan.json',sha(R/'lifecycle-plan.json'))
        self.assertEqual(Path(actual.python).resolve(),Path(sys.executable).resolve())
        ctx=wc.Context.__new__(wc.Context)
        selected={c:{'pid':10+i,'generation':c,'instance_id':c,'cohort':{'synthetic':c}} for i,c in enumerate(('nexus','connector'))}
        ctx.handles={c:{'child':SimpleNamespace(exited=lambda:False)} for c in selected};ctx.selected=selected
        ctx.base=SimpleNamespace(require_nexus_ready=lambda:selected['nexus'])
        ctx.transfer=actual;ctx.connector=SimpleNamespace(current_ready=lambda x:selected['connector'])
        with patch.object(wc,'same_cycle'),patch.object(wc,'same_owner'):
            self.assertEqual(ctx.require_ready(),selected)

    def post_fixture(self,root):
        from recovery_context import RecoveryContext
        sys.path.insert(0,str(R/'post-svc20'))
        from post_context import Context as PostContext
        base=RecoveryContext.__new__(RecoveryContext);base.PUBLIC=root/'public';base.PUBLIC.mkdir()
        base.plan_sha256='lifecycle-plan'
        post=PostContext.__new__(PostContext);post.base=base;post.PUBLIC=root/'post-svc20/public';post.PUBLIC.mkdir(parents=True)
        post.plan_sha256=base.plan_sha256;post.post_plan_sha256='post-plan';post.scope=self.doc['remote_scope']
        post.post_plan={'basis':{'completed':{'path':'done','sha256':'done-hash'},
            'rotation':{'path':'rotation','sha256':'rotation-hash'}}}
        ctx=wc.Context.__new__(wc.Context);ctx.P=deepcopy(self.plan);ctx.binding_scope=self.doc['remote_scope']
        ctx.P['post_svc20_plan']={'sha256':'post-plan'}
        ctx.P['prerequisites']['completed_profile']={'path':'done','sha256':'done-hash'}
        ctx.selected={}
        for component,owner in (('nexus',base),('connector',post)):
            cohort={role:{'pid':i+1,'birth':i+100} for i,role in enumerate(wc.ROLES)}
            ctx.selected[component]={'cohort':cohort}
            for suffix,file_suffix in (('selection','owner-selection'),('watch_started','exit-watch-started')):
                path=owner.PUBLIC/(component+'-'+file_suffix+'.json')
                value={'lifecycle_plan_sha256':'lifecycle-plan','cohort':cohort,'retained_roles':list(wc.ROLES),'observer':{'pid':99,'birth':1000}}
                if component=='connector':value['post_svc20_plan_sha256']='post-plan'
                path.write_text(json.dumps(value))
                ctx.P['prerequisites'][component+'_'+suffix]={'path':str(path),'sha256':wc.sha(path)}
        return ctx,post

    def test_fresh_post_namespace_and_dual_tags_required_before_paid_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx,post=self.post_fixture(Path(tmp))
            wc.bind_post_svc20(ctx,post)
            self.assertIs(ctx.base,post.base);self.assertIs(ctx.transfer,post)
            source=ctx.P['prerequisites']['connector_selection'];path=Path(source['path'])
            value=json.loads(path.read_text());value.pop('post_svc20_plan_sha256');path.write_text(json.dumps(value));source['sha256']=wc.sha(path)
            with self.assertRaisesRegex(RecoveryRefused,'POST_SVC20_RECEIPT_PLAN_CHANGED'):wc.bind_post_svc20(ctx,post)
            old=post.base.PUBLIC/'connector-owner-selection.json';old.write_text(json.dumps(value))
            ctx.P['prerequisites']['connector_selection']={'path':str(old),'sha256':wc.sha(old)}
            with self.assertRaisesRegex(wc.require.__globals__['Refused'],'FRESH_OBSERVER_NAMESPACE_REQUIRED'):wc.bind_post_svc20(ctx,post)

    def test_old_connector_exit_does_not_replace_fresh_watch_or_exit_proof(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx,post=self.post_fixture(Path(tmp));wc.bind_post_svc20(ctx,post)
            for component,owner in (('nexus',post.base),('connector',post.base)):
                cohort=ctx.selected[component]['cohort']
                proof={'lifecycle_plan_sha256':'lifecycle-plan','force_used':False,'cohort':cohort,
                    'exits':{role:dict(value,physical_exit=True) for role,value in cohort.items()}}
                (owner.PUBLIC/(component+'-exit-proof.json')).write_text(json.dumps(proof))
            observed=[]
            def process(pid):
                observed.append(pid);return SimpleNamespace(birth=1000,exited=lambda:False,close=lambda:None)
            with patch.object(wc,'Process',side_effect=process):result=ctx._external_watchers()
            self.assertTrue(result['nexus']['physical_exit_confirmed']);self.assertIn('observer',result['connector'])
            self.assertEqual(observed,[99])
            proof=json.loads((post.base.PUBLIC/'connector-exit-proof.json').read_text())
            proof['post_svc20_plan_sha256']='post-plan'
            (post.PUBLIC/'connector-exit-proof.json').write_text(json.dumps(proof))
            result=ctx._external_watchers();self.assertTrue(result['connector']['physical_exit_confirmed'])

if __name__=='__main__':unittest.main(verbosity=2)
